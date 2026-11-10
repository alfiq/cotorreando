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

Cuando hay un conjunto coherente de cambios en `main`, las pruebas pasan y el instalador se
construye y se probó a mano en una PC. No hace falta esperar a juntar mucho: es mejor una
versión pequeña que funciona que una grande a medias.

## Pasos

1. **Cambiar la versión.** Con el script:

   ```powershell
   python scripts/bump_version.py 0.0.9
   ```

   Escribe la versión en los cuatro lugares donde vive y agrega a `CHANGELOG.md` un
   encabezado vacío `## 0.0.9 — AAAA-MM-DD`. A mano, son estos:

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

4. **Construir** con `.\build.ps1`. Deja `dist\Cotorreando-0.0.9-setup.exe`. Instálalo y
   pruébalo encima de la versión anterior.

5. **Unir a `main`** (PR o merge) y hacer commit de la versión si no estaba.

6. **Etiquetar y subir.**

   ```powershell
   git checkout main
   git pull
   git tag v0.0.9
   git push origin main --tags
   ```

7. **Crear el Release en GitHub** sobre la etiqueta `v0.0.9`, con el texto del CHANGELOG y el
   `setup.exe` adjunto:

   ```powershell
   gh release create v0.0.9 dist\Cotorreando-0.0.9-setup.exe --title "0.0.9" --notes-file notas.md
   ```

   Al publicarse, el workflow `instalador-fijo.yml` sube una copia con el nombre fijo
   `Cotorreando-setup.exe`, que es a lo que apunta el botón de descarga del sitio
   (`releases/latest/download/Cotorreando-setup.exe`). No hay que subirla a mano.

   No lo marques como borrador ni como pre-release: la búsqueda de actualizaciones de la app
   pregunta por `releases/latest`, que ignora ambos, y compara su etiqueta (sin la `v`) con la
   versión instalada. Una etiqueta que no sea `vX.Y.Z` se ignora.

## Botón de descarga del sitio

La portada del sitio de documentación abre con un botón que descarga el instalador más reciente.
El bloque (texto y estilos) está en `docs/conf.py`, en `DESCARGA` y en la hoja `CSS`.

Cómo funciona:

1. El botón apunta a
   `https://github.com/alfiq/cotorreando/releases/latest/download/Cotorreando-setup.exe`. GitHub
   redirige esa dirección al archivo con ese nombre de la última Release publicada (ni borradores
   ni pre-releases).
2. `build.ps1` deja el instalador con la versión en el nombre (`Cotorreando-X.Y.Z-setup.exe`), y
   es el único que se sube a mano con `gh release create`.
3. Al publicarse la Release, el workflow `.github/workflows/instalador-fijo.yml` descarga ese
   instalador y lo vuelve a subir a la misma Release como `Cotorreando-setup.exe`. Da igual si es
   parche, menor o mayor.

Comprobar que funciona, tras publicar:

```bash
curl -sIL -o /dev/null -w "%{http_code}
" https://github.com/alfiq/cotorreando/releases/latest/download/Cotorreando-setup.exe
```

Tiene que dar `200`. Si da `404`, a la última Release le falta el archivo con nombre fijo (el
workflow falló o la Release se creó antes de que existiera). Se arregla lanzándolo a mano con la
etiqueta; se puede repetir sin problema, porque reemplaza el archivo si ya estaba:

```bash
gh workflow run instalador-fijo.yml -f tag=vX.Y.Z
```

No hay que renombrar el instalador de `installer.iss` ni subir la copia a mano: el nombre con
versión lo usan las personas que bajan una versión concreta, y el fijo solo existe para el botón.

## Sumas de verificación

Cada Release trae también `SHA256SUMS.txt`, que el mismo workflow sube con las sumas del
instalador con versión y del fijo, en el formato `<sha256>  <archivo>`. Para comprobar una
descarga, en PowerShell:

```powershell
Get-FileHash Cotorreando-setup.exe -Algorithm SHA256
```

Compara el valor `Hash` (en minúsculas o mayúsculas, da igual) con la línea de
`SHA256SUMS.txt` que termina en `Cotorreando-setup.exe`. Si no coinciden, no ejecutes el
instalador y vuelve a bajarlo.

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
