# Offline Help maintenance

English Markdown is the source language. Keep the Traditional Chinese documents
semantically aligned with it. The canonical Help sources are:

- [CLI User Guide](../cli/USER_GUIDE.md) and [繁體中文](../cli/USER_GUIDE.zh-TW.md)
- [WebUI and Desktop User Guide](../webui/USER_GUIDE.md) and [繁體中文](../webui/USER_GUIDE.zh-TW.md)
- [Supported Models](../core/supported-models.md) and [繁體中文](../core/supported-models.zh-TW.md)

`template.html` and `help.css` render these six documents without network
dependencies. Install the existing development extra before generating Help:

```powershell
uv sync --all-extras --locked --link-mode=copy
.venv\Scripts\python scripts/generate_help.py --output-dir .tmp_tests/generated_help
```

The generator writes six HTML files and one shared CSS file into staging.
Inspect this output before copying the required files into the runtime packages:

```powershell
$staging = ".tmp_tests/generated_help"
$cliHelp = "src/scopes_tool_cli/help"
$webHelp = "src/scopes_tool_webui/static/help"
New-Item -ItemType Directory -Force $cliHelp, $webHelp | Out-Null
foreach ($name in @("cli.html", "cli.zh-TW.html", "supported-models.html", "supported-models.zh-TW.html", "help.css")) {
    Copy-Item -LiteralPath (Join-Path $staging $name) -Destination $cliHelp -Force
}
foreach ($name in @("webui.html", "webui.zh-TW.html", "supported-models.html", "supported-models.zh-TW.html", "help.css")) {
    Copy-Item -LiteralPath (Join-Path $staging $name) -Destination $webHelp -Force
}
```

Commit the regenerated runtime files together with their Markdown/template/CSS
changes. Never edit generated HTML directly. The generation test checks all
local links and byte-for-byte synchronization with staging. Links between
canonical documents become local HTML links. Links to local documents outside
the bundled Help set fail generation; keep maintainer references in engineering
documents rather than showing repository paths to installed users.

CLI opens its bundled file directly and needs no VISA or server. WebUI serves
its existing `/static/help/` assets with `Cache-Control: no-store`. Desktop
shares these WebUI assets and only opens approved same-origin Help pages in the
system browser. Its local Host must remain running while Help is used.

Help reuses `scopes-tool.webui.theme` and the `system`, `light`, `dark`
preferences. The WebUI passes its preference in the URL; Electron passes its
validated native theme preference to the external browser. System mode follows
OS color-scheme changes. Help does not create a separate preference store.

Validate the affected CLI, WebUI, Desktop, documentation, and packaging tests
as described in [Testing Guidelines](../testing-guidelines.md) and
[WebUI Change Rules](../webui/web-ui-change-rules.md). Build Wheel and Windows
onedir artifacts to verify packaged Help; mocked packaging tests alone do not
establish that the executable bundle works.
