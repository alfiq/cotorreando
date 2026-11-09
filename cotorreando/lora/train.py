"""LoRA fine-tuning of Parakeet TDT on the user's recordings.

Runs inside the optional training environment (PyTorch + NeMo), never inside
the app itself, so it must not import the ``cotorreando`` package.

Low-rank adapters are added, by default, to the attention (q/k/v/out) and feed-forward
projections of every Conformer layer (``--targets`` changes that). Only the adapters are trained; afterwards they
are merged into the base weights and the model is exported to ONNX (int8) in
the same layout the app already loads. A few recordings are held out to compare
the error rate before and after; if training did not help, nothing is exported.

Recordings arrive through stdin, so decrypted audio stays out of the disk. A line
``STOP`` on stdin saves the state in ``--checkpoint`` (encrypted) and ends the run; a later
run over the same recordings continues from there.

    python train.py --base-onnx DIR --checkpoint FILE --out DIR < job
    python train.py --export-only --out DIR
"""

import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import threading
from pathlib import Path

import numpy as np
import torch
from torch import nn

BASE_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
# A .nemo carries a config that Hydra instantiates, so the file must be exactly this one.
BASE_REVISION = "541d1f99c6b0c3cd0b11a95167540bb8edefd82b"
BASE_FILE = "parakeet-tdt-0.6b-v3.nemo"
BASE_SHA256 = "3cbdc85877e668ca7b82d0d56770eb1fac76691f55d6b97545e8d61ca588d10d"
# Where adapters can go in each Conformer layer: (submodules, projections inside them).
GROUPS = {
    "attn": (("self_attn",), ("linear_q", "linear_k", "linear_v", "linear_out")),
    "ffn": (("feed_forward1", "feed_forward2"), ("linear1", "linear2")),
    "conv": (("conv",), ("pointwise_conv1", "pointwise_conv2")),   # 1x1 Conv1d
}
COPIED = ("nemo128.onnx", "vocab.txt", "config.json")
DURATIONS = 5       # the model predicts frame skips 0..4
RATE = 16000
MAX_SECONDS = 30
CHECKPOINT_EVERY = 25
VERIFY_MARGIN = 0.05  # per-frame cost a corrected text may add over the original


class LoRALinear(nn.Module):
    """y = W x + (alpha / r) * B A x, with W frozen and B initialised to zero.

    ``base`` is an nn.Linear or a 1x1 nn.Conv1d, whose input is (batch, channels, time).
    """

    def __init__(self, base: nn.Module, rank: int, alpha: float, init: str = "small", dropout: float = 0.0):
        super().__init__()
        self.pointwise = isinstance(base, nn.Conv1d)
        if self.pointwise and (base.kernel_size != (1,) or base.groups != 1):
            raise ValueError("only 1x1 convolutions can take an adapter")
        self.base = base
        self.scale = alpha / rank
        out_features, in_features = base.weight.shape[:2]
        device = base.weight.device
        self.a = nn.Parameter(torch.empty(rank, in_features, device=device))
        self.b = nn.Parameter(torch.zeros(out_features, rank, device=device))
        if init == "kaiming":      # what PEFT uses
            nn.init.kaiming_uniform_(self.a, a=math.sqrt(5))
        else:
            nn.init.normal_(self.a, std=0.01)
        self.drop = nn.Dropout(dropout) if dropout else nn.Identity()

    def delta(self) -> torch.Tensor:
        return (self.b @ self.a) * self.scale

    def forward(self, x):
        if self.pointwise:
            low = torch.einsum("rc,bct->brt", self.a, self.drop(x))
            return self.base(x) + torch.einsum("or,brt->bot", self.b, low) * self.scale
        return self.base(x) + (self.drop(x) @ self.a.t() @ self.b.t()) * self.scale

    def merged(self) -> nn.Module:
        with torch.no_grad():
            delta = self.delta().to(self.base.weight.dtype)
            self.base.weight += delta[..., None] if self.pointwise else delta
        return self.base


def adapter_sites(model, targets: str = "attn", layers: str = "all"):
    """(parent module, attribute name) of every projection to adapt."""
    chosen = list(model.encoder.layers)
    if layers != "all":
        first, last = (int(n) for n in layers.split("-"))
        chosen = chosen[first:last + 1]
    for layer in chosen:
        for group in targets.split(","):
            parents, names = GROUPS[group]
            for parent in parents:
                for name in names:
                    yield getattr(layer, parent), name


def add_lora(model, rank: int, alpha: float, targets: str = "attn", layers: str = "all",
             init: str = "small", dropout: float = 0.0) -> None:
    for p in model.parameters():
        p.requires_grad = False
    for parent, name in adapter_sites(model, targets, layers):
        setattr(parent, name, LoRALinear(getattr(parent, name), rank, alpha, init, dropout))


def lora_modules(model) -> list[LoRALinear]:
    return [m for m in model.modules() if isinstance(m, LoRALinear)]


def merge_lora(model) -> None:
    for parent in list(model.modules()):
        for name, child in list(parent.named_children()):
            if isinstance(child, LoRALinear):
                setattr(parent, name, child.merged())


def _tdt_forward_backward(emit, blank, dur, backward: bool):
    """Log-likelihood and, if ``backward``, the expected use of each log-probability (numpy fp64 arrays)."""
    frames, length = emit.shape
    add = np.logaddexp
    stay = emit + dur[:, :length, 0]
    prefix = np.zeros((frames, length + 1))
    prefix[:, 1:] = np.cumsum(stay, 1)
    leave = (blank[..., None] + dur[..., 1:]).transpose(0, 2, 1)     # frame, d - 1, cell
    move = (emit[..., None] + dur[:, :length, 1:]).transpose(0, 2, 1)
    reach = leave.shape[1]
    alpha = np.full((frames + 1, length + 1), -1e4)      # a floor: the cost of a hopeless text is capped
    alpha[0, 0] = 0.0
    rows = np.empty((frames, length + 1))
    for t in range(frames):
        rows[t] = row = prefix[t] + add.accumulate(alpha[t] - prefix[t])   # zero-duration tokens, in closed form
        out = leave[t] + row
        out[:, 1:] = add(out[:, 1:], move[t] + row[:-1])
        k = min(reach, frames - t)
        alpha[t + 1:t + 1 + k] = add(alpha[t + 1:t + 1 + k], out[:k])
        if k < reach:                                                      # skips past the end land on the last frame
            alpha[frames] = add(alpha[frames], add.reduce(out[k:], 0))
    z = alpha[frames, length]
    if not backward:
        return z, ()
    beta = np.full((frames + 1, length + 1), -np.inf)
    beta[frames, length] = 0.0
    target = np.minimum(np.arange(frames)[:, None] + np.arange(1, reach + 1)[None], frames)
    for t in range(frames - 1, -1, -1):
        after = beta[target[t]]
        out = leave[t] + after
        out[:, :length] = add(out[:, :length], move[t] + after[:, 1:])
        beta[t] = add.accumulate((add.reduce(out, 0) + prefix[t])[::-1])[::-1] - prefix[t]
    after = beta[target]
    use_stay = np.exp(rows[:, :length] + stay + beta[:frames, 1:] - z)
    use_step = np.exp(rows[:, None] + leave + after - z)
    use_move = np.exp(rows[:, None, :length] + move + after[:, :, 1:] - z)
    use_dur = np.zeros_like(dur)
    use_dur[:, :length, 0] = use_stay
    use_dur[:, :, 1:] = use_step.transpose(0, 2, 1)
    use_dur[:, :length, 1:] += use_move.transpose(0, 2, 1)
    return z, (use_stay + use_move.sum(1), use_step.sum(1), use_dur)


def tdt_cost(acts, labels, frames: int, length: int, durations: int):
    """Negative log-likelihood of one utterance: the forward algorithm over (frame, label).

    From each cell a blank advances 1..D-1 frames; a token advances 0..D-1 frames and one label.
    The gradient of a log-likelihood is the expected use of each log-probability: forward-backward
    gives that directly, so autograd only has to carry it back from the log-probabilities.
    """
    tokens = acts.size(-1) - durations
    wants_grad = torch.is_grad_enabled() and acts.requires_grad
    acts = acts[:frames, :length + 1]                    # without the batch's padding
    tok = torch.log_softmax(acts[..., :tokens], -1)
    dur = torch.log_softmax(acts[..., tokens:], -1)
    logs = (tok[:, torch.arange(length, device=acts.device), labels[:length]],   # label u from cell u
            tok[..., tokens - 1], dur)
    logs = tuple(x.clamp_min(-1e4) for x in logs)        # -inf would turn the expected uses into NaN
    z, uses = _tdt_forward_backward(*(x.detach().double().cpu().numpy() for x in logs), wants_grad)
    if not wants_grad:
        return -dur.new_tensor(z) / frames
    # Value z, gradient sum(use * d log-probability).
    expected = sum((torch.from_numpy(u).to(x.device, x.dtype) * x).sum() for u, x in zip(uses, logs))
    return -(expected - expected.detach() + float(z)) / frames


def use_portable_loss(model) -> None:
    """NeMo's TDT loss needs numba's CUDA backend, whose nvvm.dll pip does not ship on Windows."""
    def forward(acts, labels, act_lens, label_lens):
        acts = acts.float()
        return torch.stack([tdt_cost(acts[i], labels[i], int(act_lens[i]), int(label_lens[i]), DURATIONS)
                            for i in range(acts.size(0))])

    model.loss._loss.forward = forward  # noqa: SLF001
    # One by one: otherwise the joint also computes the whole batch's padding rows, and the
    # VRAM it reserves can outgrow the card and start paging.
    model.joint._fused_batch_size = 1  # noqa: SLF001


class Readings(torch.utils.data.Dataset):
    """Recordings held in memory: decrypted audio never touches the disk."""

    def __init__(self, model, rows: list[dict]):
        self.items = [(torch.from_numpy(r["audio"]), torch.tensor(model.tokenizer.text_to_ids(r["text"])))
                      for r in rows if r["audio"].size <= MAX_SECONDS * RATE]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]

    @staticmethod
    def collate(batch):
        audio, tokens = zip(*batch)
        return (nn.utils.rnn.pad_sequence(audio, batch_first=True), torch.tensor([a.numel() for a in audio]),
                nn.utils.rnn.pad_sequence(tokens, batch_first=True), torch.tensor([t.numel() for t in tokens]))


def adapter_state(model) -> dict:
    return {k: v.detach().cpu() for k, v in model.named_parameters() if v.requires_grad}


def save_checkpoint(path: Path, key: bytes, digest: str, step: int, model, optimizer) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    buffer = io.BytesIO()
    torch.save({"digest": digest, "step": step, "adapters": adapter_state(model),
                "optimizer": optimizer.state_dict()}, buffer)
    nonce = os.urandom(12)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(nonce + AESGCM(key).encrypt(nonce, buffer.getvalue(), None))
    temp.replace(path)


def load_checkpoint(path: Path, key: bytes, digest: str) -> dict | None:
    """The saved state, if there is one for exactly this dataset."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        data = path.read_bytes()
        state = torch.load(io.BytesIO(AESGCM(key).decrypt(data[:12], data[12:], None)), weights_only=True)
    except (OSError, InvalidTag, ValueError):
        return None
    return state if state["digest"] == digest else None


def train(model, rows: list[dict], steps: int, lr: float, stopping: threading.Event, checkpoint: Path,
          key: bytes, digest: str, sched: str = "constant") -> bool:
    """Returns False if it stopped early, with its state saved in ``checkpoint``."""
    import lightning.pytorch as pl

    use_portable_loss(model)
    saved = load_checkpoint(checkpoint, key, digest)
    done = 0
    if saved:
        model.load_state_dict(saved["adapters"], strict=False)
        done = saved["step"]
        print(f"RESUMED {done}", flush=True)
    if done >= steps:
        return True
    model._train_dl = torch.utils.data.DataLoader(Readings(model, rows), batch_size=4, shuffle=True,  # noqa: SLF001
                                                  collate_fn=Readings.collate, drop_last=False)
    optim = {"name": "adamw", "lr": lr, "weight_decay": 0.0}
    if sched == "cosine":
        # A resumed run restarts the schedule; only the sweep uses it so far, and it never resumes.
        optim["sched"] = {"name": "CosineAnnealing", "warmup_ratio": 0.1, "min_lr": 0.0, "max_steps": steps}
    model.setup_optimization(optim)
    model._validation_dl = None  # noqa: SLF001 - we have no validation split
    gpu = torch.cuda.is_available()

    class Progress(pl.Callback):
        def on_train_start(self, trainer, *_):
            if saved:
                trainer.optimizers[0].load_state_dict(saved["optimizer"])

        def on_train_batch_start(self, *_):
            # A few minutes of audio must not shift the normalisation statistics.
            for module in model.modules():
                if isinstance(module, nn.modules.batchnorm._BatchNorm):  # noqa: SLF001
                    module.eval()

        def on_train_batch_end(self, trainer, *_):
            step = done + trainer.global_step
            print(f"PROGRESS {step} {steps}", flush=True)
            if stopping.is_set() or step % CHECKPOINT_EVERY == 0:
                save_checkpoint(checkpoint, key, digest, step, model, trainer.optimizers[0])
            if stopping.is_set():
                trainer.should_stop = True

    # log_every_n_steps past the last step: at each one NeMo would decode the batch for a WER nobody reads.
    trainer = pl.Trainer(max_steps=steps - done, accelerator="gpu" if gpu else "cpu", devices=1,
                         precision="bf16-mixed" if gpu else "32-true", logger=False,
                         enable_checkpointing=False, log_every_n_steps=steps - done + 1, limit_val_batches=0,
                         callbacks=[Progress()], enable_progress_bar=False)
    model.set_trainer(trainer)
    trainer.fit(model)
    if gpu:
        model.cuda()               # Lightning leaves the model on the CPU
    return not stopping.is_set()


def text_cost(model, audio, text: str) -> float:
    """How badly ``text`` explains ``audio``, per frame. Lower is better."""
    device = next(model.parameters()).device
    labels = torch.tensor(model.tokenizer.text_to_ids(text), device=device)
    signal = torch.from_numpy(audio).to(device)[None]
    encoded, frames = model.forward(input_signal=signal, input_signal_length=torch.tensor([signal.size(1)], device=device))
    decoded, _, _ = model.decoder(targets=labels[None], target_length=torch.tensor([labels.numel()], device=device))
    acts = model.joint.joint(encoded.transpose(1, 2), decoded.transpose(1, 2))
    return float(tdt_cost(acts[0].float(), labels, int(frames[0]), labels.numel(), DURATIONS))


def verify_corrections(model, rows: list[dict]) -> list[dict]:
    """Keep a correction only if the corrected text explains the audio about as well as the original."""
    was_training = model.training
    model.eval()
    kept = []
    with torch.no_grad():
        for row in rows:
            if row.get("kind") == "correction" and not row.get("verified"):
                accepted = text_cost(model, row["audio"], row["text"]) <= (
                    text_cost(model, row["audio"], row["old"]) + VERIFY_MARGIN)
                print(f"VERIFY {row['id']} {int(accepted)}", flush=True)
                if not accepted:
                    continue
            kept.append(row)
    model.train(was_training)
    return kept


def read_job() -> tuple[bytes, list[dict]]:
    """A JSON line (the checkpoint key and the rows), then each row's audio as float32."""
    source = sys.stdin.buffer
    job = json.loads(source.readline())
    for row in job["rows"]:
        data = source.read(row["samples"] * 4)
        row["audio"] = np.frombuffer(data, np.float32).copy()
    return bytes.fromhex(job["key"]), job["rows"]


def watch_for_stop(stopping: threading.Event) -> None:
    def watch():
        for line in sys.stdin.buffer:
            if line.strip() == b"STOP":
                stopping.set()

    threading.Thread(target=watch, daemon=True).start()


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", "", text.lower()).split()


def _edits(a: list[str], b: list[str]) -> int:
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def word_error_rate(model, rows: list[dict]) -> float:
    was_training = model.training
    model.eval()
    results = model.transcribe([r["audio"] for r in rows], batch_size=2, verbose=False)
    if was_training:
        model.train()
    errors = sum(_edits(_words(r["text"]), _words(h.text)) for r, h in zip(rows, results))
    return errors / max(sum(len(_words(r["text"])) for r in rows), 1)


ENCODER, DECODER = "encoder-model.int8.onnx", "decoder_joint-model.int8.onnx"


def onnx_node_name(module_name: str, pointwise: bool) -> str:
    """'layers.3.self_attn.linear_q' -> '/layers.3/self_attn/linear_q/MatMul_quant', as quantize_dynamic names it."""
    layer, index, *rest = module_name.split(".")
    return f"/{layer}.{index}/{'/'.join(rest)}/{'Conv' if pointwise else 'MatMul'}_quant"


def graft(model, base_onnx: Path, out: Path) -> None:
    """Add each adapter to the app's int8 encoder as a parallel fp32 branch: y = W_int8 x + s B A x.

    Merging the adapters into the weights and quantizing again loses them (the change is a few
    percent of one int8 step) and a fresh NeMo export is itself worse than the app's model.
    Here the base model is exactly the app's, and the adapters are exact.
    """
    import onnx
    from onnx import helper, numpy_helper

    encoder = onnx.load(str(base_onnx / ENCODER))
    graph = encoder.graph
    producer = {o: n for n in graph.node for o in n.output}
    consumers: dict[str, list] = {}
    for n in graph.node:
        for i in n.input:
            consumers.setdefault(i, []).append(n)
    weights = {i.name: i for i in graph.initializer}
    by_name = {n.name: n for n in graph.node}
    after: dict[str, list] = {}           # node name -> new nodes to place right after it

    for name, module in model.encoder.named_modules():
        if not isinstance(module, LoRALinear):
            continue
        quant = by_name.get(onnx_node_name(name, module.pointwise))
        if quant is None:
            raise RuntimeError(f"{name}: no {onnx_node_name(name, module.pointwise)} in {ENCODER}")
        expected = tuple(module.base.weight.shape) if module.pointwise else tuple(module.base.weight.shape[::-1])
        if tuple(weights[quant.input[1]].dims) != expected:
            raise RuntimeError(f"{name}: weight {list(weights[quant.input[1]].dims)} is not {list(expected)}")
        x = producer[quant.input[0]].input[0]                  # the float input of DynamicQuantizeLinear
        cast, = consumers[quant.output[0]]
        scaled, = consumers[cast.output[0]]                     # Mul by the scales: the float result
        y = scaled.output[0]
        a = module.a.detach().float().cpu().numpy()
        b = (module.b.detach().float() * module.scale).cpu().numpy()
        p = f"lora/{name}"
        if module.pointwise:     # (batch, channels, time): 1x1 convolutions
            a, b, op = a[..., None], b[..., None], "Conv"
        else:                    # (..., features) @ (in, out)
            a, b, op = a.T.copy(), b.T.copy(), "MatMul"
        graph.initializer.extend([numpy_helper.from_array(a, f"{p}/A"), numpy_helper.from_array(b, f"{p}/B")])
        scaled.output[0] = f"{p}/base"
        after[scaled.name] = [
            helper.make_node(op, [x, f"{p}/A"], [f"{p}/low"], name=f"{p}/down"),
            helper.make_node(op, [f"{p}/low", f"{p}/B"], [f"{p}/delta"], name=f"{p}/up"),
            helper.make_node("Add", [f"{p}/base", f"{p}/delta"], [y], name=f"{p}/add"),
        ]
    if not after:
        raise RuntimeError("no adapters to graft")
    nodes = []
    for n in graph.node:
        nodes.append(n)
        nodes.extend(after.get(n.name, ()))
    del graph.node[:]
    graph.node.extend(nodes)
    onnx.checker.check_model(encoder)
    out.mkdir(parents=True, exist_ok=True)
    onnx.save(encoder, str(out / ENCODER))
    for name in (DECODER, *COPIED):
        shutil.copy2(base_onnx / name, out / name)


def module_path(node_name: str) -> str:
    """'/pre_encode/conv/conv.0/Conv_quant' -> 'pre_encode.conv.0' (the exporter repeats a parent's name)."""
    parts, path = node_name.strip("/").split("/")[:-1], []
    for part in parts:
        if path and part.startswith(path[-1] + ".") and part[len(path[-1]) + 1:].isdigit():
            part = part[len(path[-1]) + 1:]
        path.append(part)
    return ".".join(path)


def fake_dynamic_quant(x: torch.Tensor) -> torch.Tensor:
    """What onnxruntime's DynamicQuantizeLinear does to a MatMulInteger/ConvInteger input: uint8 with
    one scale per tensor (the app runs one window at a time, so: per sample here). The gradient
    passes straight through."""
    v = x.float()
    dims = tuple(range(1, v.dim()))
    lo, hi = v.amin(dims, keepdim=True).clamp(max=0), v.amax(dims, keepdim=True).clamp(min=0)
    scale = ((hi - lo) / 255).clamp(min=1e-12)
    zero = torch.round(-lo / scale).clamp(0, 255)
    q = (torch.round(v / scale) + zero).clamp(0, 255)
    return x + ((q - zero) * scale - v).to(x.dtype).detach()


class AppWeights:
    """Make the NeMo encoder compute like the app's int8 ONNX one, so that adapters are learnt for it.

    Every weight the app quantizes is replaced by its dequantized int8 value, and its input goes
    through the same dynamic uint8 quantization. Adapters read the unquantized input, as in ``graft``.
    Weights the exporter folded (a BatchNorm into the depthwise convolution) cannot be matched and
    stay as they are.
    """

    MAX_ERROR = 0.25      # relative difference that marks a folded weight rather than int8 rounding

    def __init__(self, model, base_onnx: Path):
        import onnx
        from onnx import numpy_helper

        graph = onnx.load(str(base_onnx / ENCODER)).graph
        values = {i.name: i for i in graph.initializer}
        producer = {o: n for n in graph.node for o in n.output}
        consumers: dict[str, list] = {}
        for n in graph.node:
            for i in n.input:
                consumers.setdefault(i, []).append(n)
        modules = dict(model.encoder.named_modules())
        self.swaps, self.skipped, self.on = [], [], False
        for node in graph.node:
            if node.op_type not in ("MatMulInteger", "ConvInteger"):
                continue
            path = module_path(node.name)
            module = modules.get(path)
            q = numpy_helper.to_array(values[node.input[1]]).astype(np.float32)
            zero = numpy_helper.to_array(values[node.input[3]]).astype(np.float32)
            cast, = consumers[node.output[0]]
            scaled, = consumers[cast.output[0]]
            scales = producer[scaled.input[1]]                       # x_scale * w_scale
            w_scale = next(numpy_helper.to_array(values[i]) for i in scales.input if i in values)
            weight = (q - zero) * w_scale
            weight = weight if node.op_type == "ConvInteger" else weight.T
            if module is None or tuple(module.weight.shape) != weight.shape:
                self.skipped.append(path)
                continue
            original = module.weight.detach().clone()
            app = torch.from_numpy(np.ascontiguousarray(weight)).to(original.device, original.dtype)
            norm = modules.get(path.rsplit(".", 1)[0] + ".batch_norm") if path.endswith("depthwise_conv") else None
            factor = torch.ones_like(original[:, :1, :1]) if original.dim() == 3 else 1.0
            if norm is not None:
                # The exporter folded the BatchNorm in: W' = W * gamma / sqrt(var + eps). Undo that
                # factor, so that NeMo's conv + BatchNorm compute exactly the app's int8 W'.
                factor = (norm.weight / torch.sqrt(norm.running_var + norm.eps)).detach().to(app.dtype)[:, None, None]
                app = app / factor
            # Compared as the app computes it (folded), where the int8 rounding is what it is.
            if float(((app - original) * factor).norm() / (original * factor).norm()) > self.MAX_ERROR:
                self.skipped.append(path)
                continue
            self.swaps.append((module, original, app))
            module.register_forward_pre_hook(self._quantize_input)
        self.use(True)

    def _quantize_input(self, module, args):
        if self.on:
            return (fake_dynamic_quant(args[0]), *args[1:])
        return None

    def use(self, on: bool) -> None:
        """Switch between the app's int8 behaviour and NeMo's own fp32 weights."""
        self.on = on
        with torch.no_grad():
            for module, original, app in self.swaps:
                module.weight.copy_(app if on else original)


def remove_lora(model) -> None:
    """Put the plain projections back, adapters dropped (the base weights were never touched)."""
    for parent in list(model.modules()):
        for name, child in list(parent.named_children()):
            if isinstance(child, LoRALinear):
                setattr(parent, name, child.base)


def export_fp32(model, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    model.eval()
    model.export(str(directory / "model.onnx"))  # writes encoder-model.onnx and decoder_joint-model.onnx


def quantize(fp32: Path, out: Path, base_onnx: Path | None, per_channel: bool = False) -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    out.mkdir(parents=True, exist_ok=True)
    for stem in ("encoder-model", "decoder_joint-model"):
        quantize_dynamic(fp32 / f"{stem}.onnx", out / f"{stem}.int8.onnx", weight_type=QuantType.QUInt8,
                         per_channel=per_channel, use_external_data_format=False)
    if base_onnx:
        for name in COPIED:
            shutil.copy2(base_onnx / name, out / name)


def export(model, out: Path, base_onnx: Path | None, per_channel: bool = False) -> None:
    export_fp32(model, out)
    quantize(out, out, base_onnx, per_channel)
    for leftover in out.iterdir():   # the fp32 export scatters its tensors in loose files
        if not (leftover.name.endswith(".int8.onnx") or leftover.name in COPIED):
            leftover.unlink()
    if not base_onnx:
        write_vocab(model, out)


def write_vocab(model, out: Path) -> None:
    """Needed only when exporting from scratch (no ONNX download available)."""
    vocab = model.tokenizer.vocab
    lines = [f"{tok} {i}" for i, tok in enumerate(vocab)] + [f"<blk> {len(vocab)}"]
    (out / "vocab.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    model.preprocessor.export(str(out / "nemo128.onnx"))


def load_base(name: str):
    """The pinned base model, checked byte for byte before NeMo opens it."""
    if name != BASE_MODEL:
        raise SystemExit(f"Unknown model {name!r}: only the pinned {BASE_MODEL} is allowed")
    import nemo.collections.asr as nemo_asr
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(BASE_MODEL, BASE_FILE, revision=BASE_REVISION)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    if h.hexdigest() != BASE_SHA256:
        os.remove(path)
        raise SystemExit(f"{BASE_FILE}: checksum mismatch, deleted")
    return nemo_asr.models.ASRModel.restore_from(path)


def main() -> None:
    import nemo.collections.asr as nemo_asr

    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path)
    ap.add_argument("--base-onnx", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default=BASE_MODEL)
    ap.add_argument("--rank", type=int, default=4)
    ap.add_argument("--alpha", type=float, default=8)
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--targets", default="attn,ffn", help="comma-separated: " + ", ".join(GROUPS))
    ap.add_argument("--layers", default="all", help='"all" or a range such as 0-11')
    ap.add_argument("--init", choices=("small", "kaiming"), default="small")
    ap.add_argument("--lora-dropout", type=float, default=0.0)
    ap.add_argument("--sched", choices=("constant", "cosine"), default="constant")
    ap.add_argument("--per-channel", action="store_true", help="int8 with one scale per output channel")
    ap.add_argument("--fp32-base", action="store_true",
                    help="train on NeMo's fp32 weights instead of the app's int8 ones (needs --base-onnx otherwise)")
    ap.add_argument("--export-only", action="store_true")
    args = ap.parse_args()

    if not args.export_only:
        key, rows = read_job()     # first, so that the sender never waits on a loading model
        stopping = threading.Event()
        watch_for_stop(stopping)
    model = load_base(args.model)
    if not args.export_only:
        if torch.cuda.is_available():
            model = model.cuda()
        if args.base_onnx and not args.fp32_base:
            AppWeights(model, args.base_onnx)   # learn for the int8 model the app runs, not NeMo's fp32 one
        rows = verify_corrections(model, rows)
        # The adapters' design is part of it: a checkpoint of another shape must not be resumed.
        design = f"{args.targets}|{args.layers}|{args.rank}|{args.alpha}|{args.lr}|{args.steps}|{args.sched}"
        digest = hashlib.sha256("|".join([design, *sorted(r["id"] for r in rows)]).encode()).hexdigest()
        held = [r for r in rows if r["held"]]
        before = word_error_rate(model, held)
        add_lora(model, args.rank, args.alpha, args.targets, args.layers, args.init, args.lora_dropout)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"Trainable parameters: {trainable:,}", flush=True)
        finished = train(model, [r for r in rows if not r["held"]], args.steps, args.lr, stopping,
                         args.checkpoint, key, digest, args.sched)
        if not finished:
            print("PAUSED", flush=True)
            os._exit(0)            # the stdin watcher must not delay or upset the exit
        after = word_error_rate(model, held)
        print(f"EVAL {before:.4f} {after:.4f}", flush=True)
        if after >= before:
            print("NOIMPROVE", flush=True)
            return
        print("EXPORTING", flush=True)
        if args.base_onnx:
            # The app's own int8 model stays untouched; the adapters ride beside it in fp32.
            graft(model, args.base_onnx, args.out)
            print("DONE", flush=True)
            return
        merge_lora(model)
    export(model.cpu(), args.out, args.base_onnx, args.per_channel)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
    # NeMo's native libraries can crash during interpreter shutdown, after the work is done.
    sys.stdout.flush()
    os._exit(0)
