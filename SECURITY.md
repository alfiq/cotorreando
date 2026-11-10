# Política de seguridad

## Versiones compatibles

Solo damos soporte a la última versión publicada en la sección de
[Releases](https://github.com/alfiq/cotorreando/releases). Si usas una versión anterior, actualiza
antes de reportar un problema.

## Cómo reportar una vulnerabilidad

Por favor, **no abras un issue público** ni describas la vulnerabilidad en un pull request. Así
evitamos que quien use la app quede expuesto antes de que haya un arreglo.

Repórtala en privado con la función de reporte privado de GitHub:

1. Ve a la pestaña **Security** del repositorio.
2. Pulsa **Report a vulnerability**.

También puedes ir directo a <https://github.com/alfiq/cotorreando/security/advisories/new>.

Incluye lo que puedas: versión de Cotorreando y de Windows, los pasos para reproducirla y qué
impacto crees que tiene. Revisamos los reportes lo antes que podamos. No pongas en el reporte
grabaciones ni texto dictado; si necesitas adjuntar el registro, revísalo antes, como se explica en
[CONTRIBUTING.md](CONTRIBUTING.md).

## Qué datos maneja la app

- El reconocimiento de voz corre en tu computadora con un modelo local. El audio no se sube a ningún
  servidor.
- Lo que la app aprende de tu voz (grabaciones de correcciones, lecturas de calibración y listas de
  palabras) se guarda cifrado con [age](https://age-encryption.org). La clave privada está cifrada
  con tu contraseña y, aparte, con el código de recuperación. Ver `cotorreando/vault.py`.
- La contraseña es opcional. Sin ella no se guarda nada de tu voz ni de lo que dictas.
- Las conexiones que hace la app, y para qué, están en [docs/PRIVACIDAD.md](docs/PRIVACIDAD.md).
