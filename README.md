# aws-sso-login-gui

This is a prototype to explore how AWS credentials obtained through [AWS SSO](https://docs.aws.amazon.com/singlesignon/latest/userguide/manage-your-accounts.html) could be managed without requiring the user to install the [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html). In particular, I'm interested in end-user applications for non-technical users that rely on AWS credentials. Instructing such users to configure `~/.aws/config` in a certain way, install the CLI v2, and regularly perform `aws sso login` from the command line is a terrible user experience. Instead, I'd like the following:

1. The user is directed to install the AWS SSO login GUI through an OS-appropriate installation mechanism.
2. A config file is provided to the user along with the end-user application. The user can import this file through the GUI to add the application's necessary AWS configuration.
3. The AWS SSO login GUI deals with keeping the user's AWS SSO token(s) refreshed.
4. The end-user application uses the AWS SDK's ability* to retrieve credentials using cached AWS SSO tokens.

\*Currently, only the Python SDK can load AWS SSO tokens, I think.

Note that this is a prototype, and is not ready for production use, though it does seem to be working. Its primary purpose (at the moment) is to serve as a demonstration of the utility and to generate discussion on the use case.

## Installation and use

```
$ poetry install
$ poetry shell
$ python -m aws_sso_login_gui [--log-level DEBUG|INFO] [--wsl DISTRO_NAME USER_NAME] [--test-controls] [--test-token-fetcher]
```

Import allows loading a file in the `~/.aws/config` format, that gets added to config file.

`--wsl DISTRO_NAME USER_NAME` allows you to use the AWS config inside a [WSL](https://docs.microsoft.com/en-us/windows/wsl/about) distro from the Windows host, since you can't currently use GUI tools inside WSL.

`--test-controls` allows you to manually set the time inside the app, so you can test expiration by setting the clock forward.

If you don't have an AWS SSO instance, you can use `--test-token-fetcher` to stub out the actual SSO integration.
Instead of opening the browser to an IdP's login page, it uses a Google Image search of cute animals.
It delays for a time, and then successfully logs in.
If you use `--test-controls`, you can configure the delay.
