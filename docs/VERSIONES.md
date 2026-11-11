# Versiones y lanzamientos

Cómo se numeran las versiones y qué pasos seguir para publicar una.

## Numeración: MAYOR.MENOR.PARCHE

Se usa [SemVer](https://semver.org/lang/es/). Al subir un dígito, los de su derecha vuelven a 0.

| Sube | Cuándo | Ejemplo |
|---|---|---|
| PARCHE | Correcciones y cambios pequeños que no agregan funciones. | 0.0.8 → 0.0.9 |
| MENOR | Funciones nuevas que no rompen lo que ya existe. | 0.0.9 → 0.1.0 |
| MAYOR | Cambios que rompen algo (formato de datos, ajustes, exportaciones) o la primera versión estable, 1.0.0. | 0.4.2 → 1.0.0 |

Mientras la versión empiece con **0.x**, la app está en desarrollo: lo habitual es subir el
PARCHE, y un cambio que rompe algo sube el MENOR en lugar del MAYOR. Las etiquetas de Git
llevan una `v` delante (`v0.0.9`); los archivos, no (`0.0.9`).

## Cuándo lanzar

Cuando hay un conjunto coherente de cambios en `main` y las pruebas pasan. CI construye y prueba
el instalador antes de publicarlo. No hace falta esperar a juntar mucho: es mejor una
versión pequeña que funciona que una grande a medias.

## Pasos

1. **Cambiar la versión.** Con el script:

   ```powershell
   python scripts/bump_version.py 0.0.9
   ```

   Escribe la versión en los cuatro lugares donde vive y agrega a `CHANGELOG.md` un
   encabezado vacío `## 0.0.9 — AAAA-MM-DD`. Si arriba hay una sección `## Sin publicar`, la renombra a
   ese encabezado y sus viñetas pasan a ser las notas de la versión. A mano, son estos:

   | Archivo | Línea |
   |---|---|
   | `pyproject.toml` | `version = "0.0.9"` |
   | `cotorreando/__init__.py` | `__version__ = "0.0.9"` |
   | `installer.iss` | `#define AppVersion "0.0.9"` |
   | `build.ps1` | `--product-version=0.0.9 --file-version=0.0.9` |

   `tests/test_version_consistency.py` falla si alguno quedó distinto o falta el encabezado.

2. **Escribir el CHANGELOG.** Bajo el encabezado, viñetas cortas en español, pensadas para
   quien usa la app (qué cambia para él, no cómo se programó). La versión más nueva va arriba.

3. **Probar.**

   ```powershell
   .venv\Scripts\python -m pytest -q
   ```

   Si quieres probar el instalador antes de etiquetar, `.uild.ps1` lo deja en
   `dist\Cotorreando-0.0.9-setup.exe` (hace falta Inno Setup 6). Es opcional: CI lo vuelve a
   construir. También puedes lanzar el workflow `release.yml` a mano (`gh workflow run
   release.yml`), que construye y prueba sin publicar y deja el instalador como artefacto.

4. **Commit en `main`** con la versión y el CHANGELOG (PR o merge).

5. **Etiquetar y subir.**

   ```powershell
   git checkout main
   git pull
   git tag v0.0.9
   git push origin main --tags
   ```

6. **CI publica la Release.** Al llegar la etiqueta, `.github/workflows/release.yml`:

   1. comprueba que la etiqueta coincide con la versión de `pyproject.toml`;
   2. construye con `build.ps1`, que corre `Cotorreando.exe --self-test` sobre el programa
      empaquetado y aborta si falla;
   3. pasa las pruebas;
   4. instala en silencio, corre `--self-test` sobre el programa instalado y desinstala en
      silencio;
   5. crea la Release `v0.0.9` con título `0.0.9`, las notas de su sección del CHANGELOG, y sube
      `Cotorreando-0.0.9-setup.exe`, la copia `Cotorreando-setup.exe` y `SHA256SUMS.txt`.

   Si algo falla no se publica nada: se corrige, se borra la etiqueta (`git push --delete origin
   v0.0.9` y `git tag -d v0.0.9`) y se vuelve a etiquetar.

   La Release no sale como borrador ni como pre-release: la búsqueda de actualizaciones de la app
   pregunta por `releases/latest`, que ignora ambos, y compara su etiqueta (sin la `v`) con la
   versión instalada. Una etiqueta que no sea `vX.Y.Z` se ignora.

`--self-test` también se puede correr a mano: `python -m cotorreando --self-test`, o
`Cotorreando.exe --self-test --self-test-log salida.txt` (el ejecutable no tiene consola, así que
las líneas van al archivo). Comprueba que cargan los módulos, ONNX Runtime con un modelo mínimo,
livekit, PortAudio, tokenizers, cryptography, pyrage, comtypes y Qt, sin abrir ventanas ni tocar
tus datos. Termina con código 0 si todo pasó.

## Botón de descarga del sitio

La portada del sitio de documentación abre con un botón que descarga el instalador más reciente.
El bloque (texto y estilos) está en `docs/conf.py`, en `DESCARGA` y en la hoja `CSS`.

Cómo funciona:

1. El botón apunta a
   `https://github.com/alfiq/cotorreando/releases/latest/download/Cotorreando-setup.exe`. GitHub
   redirige esa dirección al archivo con ese nombre de la última Release publicada (ni borradores
   ni pre-releases).
2. `build.ps1` deja el instalador con la versión en el nombre (`Cotorreando-X.Y.Z-setup.exe`).
3. El workflow `.github/workflows/release.yml` sube a la Release ese instalador y una copia llamada
   `Cotorreando-setup.exe`. Da igual si es parche, menor o mayor.

Comprobar que funciona, tras publicar:

```bash
curl -sIL -o /dev/null -w "%{http_code}
" https://github.com/alfiq/cotorreando/releases/latest/download/Cotorreando-setup.exe
```

Tiene que dar `200`. Si da `404`, a la última Release le falta el archivo con nombre fijo. Se
arregla subiéndolo a esa Release (reemplaza el archivo si ya estaba):

```bash
gh release download vX.Y.Z --pattern 'Cotorreando-*-setup.exe'
cp Cotorreando-X.Y.Z-setup.exe Cotorreando-setup.exe
gh release upload vX.Y.Z Cotorreando-setup.exe --clobber
```

No hay que renombrar el instalador de `installer.iss`: el nombre con versión lo usan las personas
que bajan una versión concreta, y el fijo solo existe para el botón.

## Sumas de verificación

Cada Release trae también `SHA256SUMS.txt`, que `release.yml` sube con las sumas del
instalador con versión y del fijo, en el formato `<sha256>  <archivo>`. Para comprobar una
descarga, en PowerShell:

```powershell
Get-FileHash Cotorreando-setup.exe -Algorithm SHA256
```

Compara el valor `Hash` (en minúsculas o mayúsculas, da igual) con la línea de
`SHA256SUMS.txt` que termina en `Cotorreando-setup.exe`. Si no coinciden, no ejecutes el
instalador y vuelve a bajarlo.

## winget

[winget](https://learn.microsoft.com/windows/package-manager/) es el gestor de paquetes de Windows.
Los paquetes salen del repositorio comunitario
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs), donde cada versión es un PR con
un manifiesto que apunta al instalador y a su SHA-256. Cuando Microsoft acepte el paquete,
se instalará con `winget install Alfiq.Cotorreando`.

El manifiesto usa siempre el instalador **con versión** (`Cotorreando-X.Y.Z-setup.exe`), nunca el de
nombre fijo: el fijo cambia de contenido en cada Release y el SHA-256 dejaría de coincidir. El
instalador es Inno Setup, por usuario y sin permisos de administrador. El `ProductCode` es el
`AppId` de `installer.iss` más `_is1`. Los manifiestos de la 0.1.4 están en
`winget/manifests/a/Alfiq/Cotorreando/0.1.4/`; se validan con
`winget validate --manifest <carpeta>`.

### Primera vez (a mano, solo la persona dueña del repositorio)

El job `winget` de `release.yml` solo puede actualizar un paquete que ya existe en winget-pkgs,
así que la primera versión se envía a mano. Esto no lo hace ningún workflow; un agente solo lo hace con tu aprobación explícita.

1. Haz un fork de `microsoft/winget-pkgs` en tu cuenta (`alfiq`).
2. Envía los manifiestos de la 0.1.4, con una de dos vías:
   - `wingetcreate submit winget/manifests/a/Alfiq/Cotorreando/0.1.4` (pide un token de GitHub
     la primera vez), o
   - un PR a mano desde tu fork con esa carpeta copiada en
     `manifests/a/Alfiq/Cotorreando/0.1.4/`.
3. Atiende la revisión del PR (validación automática y revisión humana de winget-pkgs) hasta que
   se acepte. Solo entonces el paquete existe en winget.
4. Crea un token de acceso personal **clásico** con el alcance `public_repo` y guárdalo en el
   repositorio `alfiq/cotorreando` como secreto `WINGET_TOKEN`
   (Settings, Secrets and variables, Actions).

### Después (automático)

Al empujar una etiqueta `vX.Y.Z`, el job `winget` corre tras `publish`: usa
[winget-releaser](https://github.com/vedantmgoyal9/winget-releaser) (fijado por SHA de commit) para
tomar el instalador con versión de la Release, calcular su SHA-256 y abrir el PR de la versión
nueva en winget-pkgs desde tu fork. Está en el mismo workflow porque las Releases creadas con
`GITHUB_TOKEN` no disparan el evento `release` de otros workflows. Sin el secreto `WINGET_TOKEN`
el job se omite con un aviso. El PR todavía lo revisa winget-pkgs; la versión llega a los usuarios
cuando lo aceptan. No hace falta tocar `winget/manifests/` en cada versión: esa carpeta es
la referencia de la primera.

## Actualizar dependencias

Las versiones exactas viven en `requirements.lock`, con hashes SHA-256; `build.ps1` y CI (Python
3.12) lo instalan tal cual. `pyproject.toml` solo lleva pisos. Para subir versiones, regenera el
archivo desde la raíz (necesita [uv](https://docs.astral.sh/uv/)):

```powershell
uv pip compile pyproject.toml --extra build --extra test --generate-hashes --python-version 3.12 --python-platform windows --upgrade -o requirements.lock
```

Luego prueba con `python -m pip install --require-hashes -r requirements.lock`, corre las
pruebas y haz commit del archivo. Si cambias las dependencias de `pyproject.toml`, regenera
también el lock. Dependabot (ecosistema `pip`) solo propone subir los pisos de `pyproject.toml`; no entiende
el formato de `requirements.lock` de uv, así que el lock se regenera a mano.

## Búsqueda de actualizaciones

La app, si está activado en Opciones › Privacidad, consulta una vez al día
`api.github.com/repos/alfiq/cotorreando/releases/latest`. Si hay una versión más nueva,
avisa junto a la burbuja con un botón para abrir la página del Release y otro para omitir
esa versión. Nunca descarga ni instala nada sola.
