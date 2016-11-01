from PIL import Image, ImageDraw, ImageFont
import random

names = ['Alpha', 'Beta', 'Gamma', 'Delta']
answers = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# generate bool table for answers
answered = []
for i in range(len(names)):
    row = []
    for j in range(len(answers)):
        row.append(random.choice([True, False]))
    answered.append(row)

# START

# create grid of results (like on doodle.com)
img_checked = Image.open('checked.png', 'r')
img_unchecked = Image.open('unchecked.png', 'r')
CELL_SIZE = max(img_checked.size)
FONT_SIZE = CELL_SIZE//2
SPACE = 20
font = ImageFont.truetype("Symbola.ttf", size=FONT_SIZE)

# get length of answers and names
longest_name = 0
for name in names:
    l = font.getsize(name)[0]
    if longest_name < l:
        longest_name = l

longest_answer = 0
for answer in answers:
    l = font.getsize(answer)[0]
    if longest_answer < l:
        longest_answer = l

# now we can create the image with optimal dimensions
dimen = (
    longest_name + len(answers)*CELL_SIZE + 3*SPACE,
    longest_answer + len(names)*CELL_SIZE + 3*SPACE
    )
# we need a square image for nicer rotating, image will get cropped later
img = Image.new("RGB", (max(dimen), max(dimen)), "#FFF")
draw = ImageDraw.Draw(img)

# draw names right aligned and vertically centered
for i in range(len(names)):
    l = font.getsize(names[i])[0]
    draw.text((SPACE + (longest_name - l), longest_answer + i*CELL_SIZE + SPACE*2 + (CELL_SIZE-FONT_SIZE)//2), names[i], "#000", font)

# draw answers rotated
img = img.rotate(-90)
draw = ImageDraw.Draw(img)

for i in range(len(answers)):
    draw.text((img.size[0] - longest_answer - SPACE, longest_name + i*CELL_SIZE + SPACE*2 + (CELL_SIZE-FONT_SIZE)//2), answers[i], "#000", font)

img = img.rotate(90)
draw = ImageDraw.Draw(img)

# draw grid
for x in range(len(answers)):
    for y in range(len(names)):
        # draw image for checked/unchecked
        offset = (x * CELL_SIZE + longest_name + SPACE*2, y * CELL_SIZE + longest_answer + SPACE*2)
        if answered[y][x]:
            img.paste(img_checked, offset)
        else:
            img.paste(img_unchecked, offset)

# crop image
img = img.crop((0, 0, dimen[0], dimen[1]))


# END

img.show()