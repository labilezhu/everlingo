






```bash
######## 圆角 #########


convert README.zh-CN.assets/cover.png \( +clone -alpha extract \
  -draw 'fill black polygon 0,0 0,30 30,0 fill white circle 30,30 30,0' \
  \( +clone -flip \) -compose Multiply -composite \
  \( +clone -flop \) -compose Multiply -composite \
  \) -alpha off -compose CopyOpacity -composite README.zh-CN.assets/cover.png


magick ~/a.jpg \
  -strip \
  \( +clone \
     -alpha extract \
     -draw "fill white roundrectangle 0,0 %[fx:w-1],%[fx:h-1],40,40" \
  \) \
  -alpha off \
  -compose CopyOpacity \
  -composite \
  ~/a.png

###### resize ###

convert "/home/labile/Downloads/ChatGPT Image Aug 8, 2026, 03_55_44 PM.png" -resize 1024x /home/labile/everlingo/README.assets/cover.png

convert "/home/labile/Downloads/ChatGPT Image Aug 8, 2026, 04_23_51 PM.png" -resize 1024x /home/labile/everlingo/README.zh-CN.assets/cover.png

```