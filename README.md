# aws-sso-login-gui

```
$ poetry install
$ poetry shell
$ python -m aws_sso_login_gui [--log-level DEBUG|INFO] [--wsl DISTRO_NAME USER_NAME] [--test-controls] [--test-token-fetcher]
```

Currently appears to be fully working.

Import allows loading a file in the `~/.aws/config` format, that gets added to config file.

`--wsl DISTRO_NAME USER_NAME` allows you to use the AWS config inside a [WSL](https://docs.microsoft.com/en-us/windows/wsl/about) distro from the Windows host, since you can't currently use GUI tools inside WSL.

`--test-controls` allows you to manually set the time inside the app, so you can test expiration by setting the clock forward.

If you don't have an AWS SSO instance, you can use `--test-token-fetcher` to stub out the actual SSO integration.
It launches the browser to a Google Images search of cute animals.
It delays for a time, and then successfully logs in.
If you use `--test-controls` will also allow the delay to be set.
