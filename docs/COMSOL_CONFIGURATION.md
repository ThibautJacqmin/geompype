# Local COMSOL connection settings

Geometry scripts can use `Project()` without embedding a workstation's server
address. Copy the public `comsol.example.json` template to `comsol.local.json`
in the directory from which you run Python:

```json
{
  "host": "localhost",
  "port": 2036
}
```

`comsol.local.json` is ignored by Git and excluded from public distributions.
The template contains only generic defaults. The file accepts only `host` and
`port`; either field may be omitted. It contains no COMSOL licence settings,
passwords or executable paths.

## Precedence and validation

Each field is resolved independently, in this order:

1. Explicit `Project(host=..., port=...)` arguments.
2. `GEOMPYPE_COMSOL_HOST` and `GEOMPYPE_COMSOL_PORT` environment variables.
3. `host` and `port` in `comsol.local.json` in the current working directory.
4. Defaults: `localhost` and `2036`.

For example, `Project(port=2040)` overrides the port while still reading the
host from the environment or file. An omitted argument, or `None`, uses these
fallbacks. The host must be a nonempty string without whitespace; the port must
be an integer from 1 to 65535. Decimal strings are accepted for ports, including
environment variable values. Invalid selected values are reported when the
Project is constructed, before connecting or generating output files.

If both fields are supplied by arguments or environment variables, the local
file is not read. Otherwise malformed JSON and unknown keys produce an error.
Settings are read once for each new Project. Editing the file does not change
an existing Project; create another Project to use the edited settings.

Launch scripts in `examples/` with the project root as your working directory
to use its local file, for example `python -i examples/example_square.py`. GeomPype does not search parent folders, the user's home
directory or the directory containing an example script.

## Connection ownership

`Project(client=existing_client)` uses the host and port of that MPh client
and bypasses the file, environment variables and explicit host/port arguments.
Constructing a Project does not connect to COMSOL. A build with a COMSOL-enabled
layer connects when needed; GDS-only geometry needs no COMSOL server.

GeomPype reuses one MPh client/JVM in a Python process. It does not silently
switch an existing connection to a different server: start a new Python session
for another server. It never starts or stops the server, disconnects the client
or clears existing models automatically. The native test runner uses these same
settings and must remain in its interactive interpreter after testing.

GUI executable paths are separate, explicit display options:
`project.show(comsol_exe=..., klayout_exe=...)`. See
[ENVIRONMENT.md](ENVIRONMENT.md) for installation and test commands.
