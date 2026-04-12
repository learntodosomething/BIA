from PIL import Image, ImageDraw

def generate_from_prompt(prompt, width, height):
    """
    IDE fogod bekötni a image.safetensors modellt.
    MOST: placeholder
    """
    img = Image.new("RGB", (width, height), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), f"PROMPT:\n{prompt}", fill=(0, 255, 200))
    return img
