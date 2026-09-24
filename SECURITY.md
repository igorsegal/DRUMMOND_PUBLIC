# Security policy

## Never commit secrets

Do not commit access tokens, broker credentials, private keys, account credentials, or private dataset access information.

The public D27 workflow uses a repository Actions secret named `DRUMMOND_DATA_TOKEN`. The value is never stored in source control.

## Private data boundary

Canonical broker/vendor market-history data remains outside this public repository. Reports of accidental market-data or credential exposure should be treated as security issues.

## External code

Pull-request code is not granted private-data credentials. The privileged D27 workflow is manual-only.
