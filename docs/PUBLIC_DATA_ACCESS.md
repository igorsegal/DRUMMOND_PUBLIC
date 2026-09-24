# Private dataset access for public research workflows

The public repository intentionally contains no canonical broker/vendor market-history dataset.

## Required secret

D27 reads the immutable dataset release from the private repository:

- private repository: `igorsegal/DRUMMOND_CLOUD`
- release tag: `dataset03-drummond_canonical_8e9a1d784e3893d9`
- dataset id: `DRUMMOND_CANONICAL_8E9A1D784E3893D9`

Create a **fine-grained personal access token** restricted to the single private repository `DRUMMOND_CLOUD` with the minimum repository permission needed to read repository contents/releases.

Add it to `DRUMMOND_PUBLIC` as an Actions repository secret named:

`DRUMMOND_DATA_TOKEN`

Do not place the token in code, workflow YAML, commit messages, issues, or logs.

## Security boundary

The D27 workflow:

- uses `workflow_dispatch` only;
- does not run on pull requests;
- gives the normal `GITHUB_TOKEN` only read permission;
- exposes `DRUMMOND_DATA_TOKEN` only to the dataset-download step;
- downloads data into the ephemeral GitHub-hosted runner;
- uploads only D27 research outputs as Actions artifacts;
- never republishes the private market-data shards.

This design keeps the code public and the canonical dataset private while allowing public-repository GitHub-hosted runners to execute the research.
