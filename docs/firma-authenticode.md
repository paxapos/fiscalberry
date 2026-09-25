# Firma Authenticode de los binarios de Windows (#176)

## Por qué

- Sin firma, Windows muestra **"Editor desconocido"** en las propiedades del
  archivo y en el cartel de UAC.
- El escenario 5 del asistente (#178) le pide a la persona un "Sí" de UAC para
  agregar una IP temporal. Ese helper **no se habilita públicamente** hasta que
  los binarios estén firmados: pedir un "Sí" sobre un editor desconocido es
  justo lo que no hay que enseñar.
- Una firma válida ayuda con los antivirus, pero no elimina sola el aviso de
  SmartScreen (ver [Qué esperar de SmartScreen](#qué-esperar-de-smartscreen)).

## Qué se firma

| Archivo | Cuándo | Por qué ahí |
|---|---|---|
| `dist\fiscalberry-gui\fiscalberry-gui.exe` | después de PyInstaller | queda firmado dentro del instalador y del zip |
| `dist\fiscalberry-cli\fiscalberry-cli.exe` | después de PyInstaller | queda firmado dentro del zip |
| `dist\FiscalberrySetup.exe` | después de Inno Setup | es lo que se descarga |

Pendiente: el desinstalador (`unins000.exe`) lo genera Inno Setup dentro del
setup al compilar. Para firmarlo hay que configurar el `SignTool` de Inno Setup
con la herramienta del proveedor. No bloquea: la instalación es por usuario y el
desinstalador no pide elevación. Las DLL y `.pyd` de `_internal` son de terceros
(Python, Kivy, SDL) y no se firman.

## Requisitos de la industria

- **La clave privada tiene que vivir en un HSM** (desde 2023): un `.pfx` en
  GitHub Secrets no sirve. Se usa un servicio de firma en la nube y en GitHub
  quedan solo las credenciales de ese servicio.
- **Validez máxima de 458 días** para certificados de firma de código emitidos
  desde el 1 de marzo de 2026 (CA/Browser Forum): hay que renovar todos los años.
  Por eso la verificación exige **sello de tiempo**: con él, la firma de un
  binario sigue siendo válida después de que vence el certificado.

## Proveedor

Situación a septiembre de 2026. Los precios son orientativos: hay que
confirmarlos al contratar.

| Servicio | ¿Disponible para una SRL argentina? | Integración con GitHub Actions | Notas |
|---|---|---|---|
| **SSL.com eSigner** (recomendado) | Sí | Action oficial [`sslcom/esigner-codesign`](https://github.com/SSLcom/esigner-codesign) | OV desde ~US$129/año más la suscripción de eSigner (~US$20/mes por credencial OV) o precio por firma. HSM FIPS 140-2 nivel 3. |
| Azure Artifact Signing (ex Trusted Signing) | **No**, salvo que haya una entidad en un país habilitado | Action oficial | El más barato. Public Trust solo para organizaciones de EE. UU., Canadá, UE, Reino Unido, Australia, Nueva Zelanda, Japón, Corea del Sur, Singapur, Suiza, Noruega e Israel. |
| DigiCert KeyLocker | Sí | Action "DigiCert Binary Signing" | Software Trust Manager se retiró en mayo de 2026. Más caro. |
| Certum (SimplySign) | Sí | Solo herramientas de la comunidad | Económico, pero la automatización en CI no es oficial. El certificado "Open Source" es para personas, no para la empresa. |

**Recomendación: SSL.com eSigner con un certificado OV** a nombre de Plus
Abstracta SRL. Es el único de la lista que combina validación para una empresa
argentina, HSM en la nube y una action oficial. EV no aporta para SmartScreen
(ver abajo), así que alcanza con OV. Si PaxaPos tuviera una entidad en un país
habilitado, Azure Artifact Signing es la alternativa más barata. Cambiar de
proveedor implica cambiar los pasos de firma de `build-release.yml`; la
verificación no cambia.

Fuentes: [Azure Artifact Signing](https://azure.microsoft.com/en-us/products/artifact-signing),
[disponibilidad por país](https://github.com/Azure/artifact-signing-action/issues/81),
[precios de eSigner](https://www.ssl.com/guide/esigner-pricing-for-code-signing/),
[eSigner con GitHub Actions](https://www.ssl.com/how-to/cloud-code-signing-integration-with-github-actions/),
[DigiCert Binary Signing en GitHub](https://docs.digicert.com/en/digicert-keylocker/ci-cd-integrations-and-deployment-pipelines/plugins/github/binary-signing-using-github-actions.html),
[Certum en la nube](https://certum.store/open-source-code-signing-on-simplysign.html).

## Qué esperar de SmartScreen

Desde marzo de 2024, un certificado EV ya no evita el aviso de SmartScreen: la
reputación se gana por volumen de descargas, igual que con OV. Los primeros
releases firmados pueden seguir mostrando el aviso hasta que el editor junte
reputación. Lo que sí cambia desde el primer día es que UAC y las propiedades
del archivo muestran el editor verificado.

## Qué hace la CI

En el job de Windows de `.github/workflows/build-release.yml`:

1. **Check Authenticode signing**: si están los cuatro secretos del servicio,
   firma. Si faltan y la variable `WINDOWS_SIGNING_REQUIRED` vale `true`, **el
   build falla**. Si faltan y no es obligatoria, sigue sin firmar con una
   advertencia visible (situación actual, hasta contratar el servicio).
2. **Sign Windows GUI / CLI**: firma los ejecutables antes de empaquetarlos.
3. **Sign Windows Installer**: firma `FiscalberrySetup.exe`.
4. **Verify Authenticode signatures**
   ([`build_tools/verify-signatures.ps1`](../build_tools/verify-signatures.ps1)):
   exige firma válida, el editor esperado (`WINDOWS_SIGNING_SUBJECT`), la huella
   exacta si se configuró (`WINDOWS_SIGNING_THUMBPRINT`), sello de tiempo y
   cadena completa. Si algo no coincide, el build falla y no se publica.

Los secretos nunca se imprimen: GitHub los enmascara, los scripts no los
muestran y la action borra sus logs (`clean_logs`). Los builds de forks y de
pull requests no tienen secretos y nunca publican: el release solo corre al
cambiar `version.py` en `v3.0.x`.

## Cómo habilitarlo (quien administra la organización)

1. Contratar en SSL.com un certificado **OV de firma de código con eSigner** a
   nombre de Plus Abstracta SRL y completar la validación de la organización.
2. En el panel de SSL.com: habilitar la firma automatizada y anotar el
   *credential ID* y el *TOTP secret*.
3. En GitHub → Settings → Secrets and variables → Actions:
   - Secretos: `ES_USERNAME`, `ES_PASSWORD`, `ES_CREDENTIAL_ID`, `ES_TOTP_SECRET`.
   - Variables: `WINDOWS_SIGNING_SUBJECT` (por ejemplo `Plus Abstracta`) y
     `WINDOWS_SIGNING_THUMBPRINT` (la huella del certificado).
4. En `build-release.yml`, fijar `sslcom/esigner-codesign@develop` al SHA de un
   commit verificado: esa action recibe las credenciales de firma.
5. Correr el workflow a mano (*workflow_dispatch*) y revisar el paso **Verify
   Authenticode signatures**. Hacerlo con una versión de `version.py` que ya
   tenga su tag: así compila y firma, pero no publica un release. Instalar el
   setup (artefacto del job) en un Windows limpio y confirmar que UAC y las
   propiedades muestran el editor.
6. Recién entonces crear la variable `WINDOWS_SIGNING_REQUIRED=true`. Desde ahí,
   un build sin firma válida falla y nunca llega a un release.

Cuando el certificado se renueve (cada año), actualizar
`WINDOWS_SIGNING_THUMBPRINT`: si no, la verificación falla, que es lo esperado.
