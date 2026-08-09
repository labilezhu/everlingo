---
name: round-corners-of-images
description: 圆角化一个 markdown 文件引用到的所有图片
metadata: []
---

# 圆角化一个 markdown 文件引用到的所有图片


## 参数

### <path_of_markdown_file>

用户给出一个 markdown 文件的路径。以下叫 <path_of_markdown_file>

## Workflow

1. 读取 <path_of_markdown_file> 文件，收集文件中所有使用到的本地文件图片文件路径
2. 对每个图片文件，执行以下指令，圆角化。

```bash
convert $path_of_image_file \( +clone -alpha extract \
  -draw 'fill black polygon 0,0 0,30 30,0 fill white circle 30,30 30,0' \
  \( +clone -flip \) -compose Multiply -composite \
  \( +clone -flop \) -compose Multiply -composite \
  \) -alpha off -compose CopyOpacity -composite $path_of_image_file
```
