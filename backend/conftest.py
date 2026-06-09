import os
import sys

# 强制把 backend/ 插入 sys.path，使 `import config` / `import models` / `import services.xxx`
# 在任何调用方式（从仓库根或 backend/ 跑 pytest）下都可用（扁平导入）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
