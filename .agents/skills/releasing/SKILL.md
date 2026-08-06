---
name: releasing
description: Release 操作
metadata: []
---

# Release 的操作规范

版本号格式规范：
The <version> format must be in the form of `X.Y.Z` or `X.Y.Z-rc.NN`, where X, Y, Z and NN are integers. 
版本号语义： `MAJOR.MINOR.PATCH[-PRERELEASE]`

## Parameters

### <version>

The release version can be provided in the user request. 
If the version is not provided: 默认取 `/VERSION_HISTORY.yaml` 中的最新一个版本，但它的 `state` 需要是 `in-progress`

Let's name the user specified release version as `<version>` for the following steps. 

### <next_version>
用户可以指定下一个版本号。以下以 `<next_version>` 作为标识。如果未指定，默认按以下规则生成 `<next_version>`：
- 如果 `<version>` 没有 rc 后缀，那么 `<next_version>` 为 `<version>` 的 PATCH+1 即： `MAJOR.MINOR.PATCH+1-rc.1]` 。 如 0.1.0 -> 0.1.1-rc.1
- 如果 `<version>` 有 rc 后缀，那么 `<next_version>` 为 `<version>` 的 PRERELEASE+1 即： `MAJOR.MINOR.PATCH-rc.PRERELEASE+1]`。 如 0.1.1-rc.1 -> 0.1.1-rc.2

## Workflow

1. Verify the <version> format is correct. If the <version> format is incorrect, the system will ask the user to provide a valid version.
2. Find the <version> in the `/VERSION_HISTORY.yaml` file. And ensure version exists:
  ```yaml
  - version: <version>
  ```
  - If found, ensure the state is not `released`. If the state is `released`, release operation will be aborted. The system should tell the reason to the
  - If not found, create it in the `/VERSION_HISTORY.yaml` file.
3. Update version number in files(skip the missing files and report to user):
   1. Replace `EVERLINGO_VER` env variable :
     - /home/labile/diy-log/home-lab/pi4ub/everlingo/router-master@container/68-multiple-user-auth-deployment.md
     - /user-docs/deployment/simple-single-deployment.md
     - /user-docs/deployment/multiple-user-auth-deployment.md
     - /README.md
   2. Replace `everlingo_version` variable :
      1. src/everlingo/mem/vault/templates/default/spec/vault_spec.md
    3. Replace version literals in source code (non-doc) — skip missing files and report to user:
      1. src/everlingo/__init__.py — replace `__version__ = "..."` with `__version__ = "<version>"`
      2. web/src/me/MePage.tsx — replace the line `EverLingo 版本： ...` with `EverLingo 版本： <version>`
      3. src/everlingo/ws_master/app.py — replace `version="..."` with `version="<version>"`
       4. src/everlingo/ws_router/app.py — replace `version="..."` with `version="<version>"`
   4. Chrome Extension 更新 Chrome 扩展版本号（关键约束）：
      - Chrome 的 `manifest.json` 的 `version` 字段**仅支持 1~4 个用点分隔的整数**（如 `0.1.1`），**不支持** semver 的预发布后缀（如 `-rc.4`）。任何带连字符的版本号在 Web Store 上传和本地 `chrome://extensions` 加载解压包时都会报 "Invalid value for 'version'" 而拒绝加载。
      - 因此需对 `<version>` 做如下转换后再写入文件：
        - 若 `<version>` 为正式版 `X.Y.Z`：manifest 与 package.json 均写 `X.Y.Z`。
        - 若 `<version>` 为预发布版 `X.Y.Z-rc.N`：
          - extension/public/manifest.json（必改）— 把 rc 次数编码为第 4 段整数：`"version": "X.Y.Z.N"`（如 `0.1.1-rc.4` → `"0.1.1.4"`）。这是 Chrome 实际读取并决定加载/更新顺序的版本号。
          - extension/package.json（建议同步）— 保留 semver 原值 `"version": "X.Y.Z-rc.N"`，npm 合法。
      - extension/package-lock.json（自动）：运行 `npm install` 会自动同步 root 的 version，无需手改。
      - 验证：用 `node -e "console.log(JSON.parse(require('fs').readFileSync('extension/public/manifest.json')).version)"` 确认 manifest 输出为整数形式（如 `0.1.1.4`），并把 build 产物作为解压包加载到 `chrome://extensions` 确认无 version 报错。

 4. Check file `/home/labile/diy-log/home-lab/hp/everlingo/130-release.sh` exists. If not, the system will abort the release operation and tell the reason to the user. 
5. Ask for a confirm and run:
  ```bash
  EVERLINGO_VER=<version> mark-specific/local-deploy/130_deploy/130-release.sh
  ```

1. Find the <version> in the `/VERSION_HISTORY.yaml` file. And update state:
  ```yaml
  - version: <version>
  - state: released
  ```  

1. 在 `/VERSION_HISTORY.yaml` 是最开头，插入下一版本号： 
   ```yaml
   - version: <next_version>
   - state: in-progress
   ```
   
