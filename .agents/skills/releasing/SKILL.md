---
name: releasing
description: Release 操作
metadata: []
---

# Release 的操作规范

The release version must be provided in the user request. If the version is not provided, the system will ask the user to provide it:
- Ask the user for:
   - release version

Let's name the user specified release version as `<version>` for the following steps. 

## Workflow

1. Verify the <version> format is correct. The <version> format must be in the form of `X.Y.Z` or `X.Y.Z-rc.NN`, where X, Y, Z and NN are integers. If the <version> format is incorrect, the system will ask the user to provide a valid version.
2. Find the <version> in the `/VERSION_HISTORY.yaml` file. And ensure version exists:
  ```yaml
  - version: <version>
  ```
  - If found, ensure the state is not `released`. If the state is `released`, release operation will be aborted. The system should tell the reason to the
  - If not found, create it in the `/VERSION_HISTORY.yaml` file.
3. Update version number in files(skip the missing files and report to user):
   1. Replace `EVERLINGO_VER` env variable :
     - /mark-specific/local-deploy/68_deploy/router-master@container/68-multiple-user-auth-deployment.md
     - /user-docs/deployment/simple-single-deployment.md
     - /user-docs/deployment/multiple-user-auth-deployment.md
     - /README.md
   2. Replace `everlingo_version` variable :
      1. src/everlingo/mem/vault/templates/default/spec/vault_spec.md
4. Check file `mark-specific/local-deploy/130_deploy/130-release.sh` exists. If not, the system will abort the release operation and tell the reason to the user. 
5. Ask for a confirm and run:
  ```bash
  EVERLINGO_VER=<version> mark-specific/local-deploy/130_deploy/130-release.sh
  ```

6. Find the <version> in the `/VERSION_HISTORY.yaml` file. And update state:
  ```yaml
  - version: <version>
  - state: released
  ```  
   
