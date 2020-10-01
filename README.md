# aws-sso-login-gui

```
$ poetry install
$ poetry shell
$ python -m aws_sso_login_gui [--log-level DEBUG|INFO] [--fake-config CONFIG_FILE] [--fake-token-fetcher] [--token-fetcher-controls]
```

Currently appears to be fully working.

Import allows loading a file in the `~/.aws/config` format, that gets added to config file.

`--fake-token-fetcher` stubs out the actual SSO integration. It launches the browser to a Google Images search of cute animals. It delays for a time, and then successfully logs in.

`--token-fetcher-controls` also manually setting the current time, so that you can test your token expiration.
