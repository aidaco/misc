import os
import io

from openai import OpenAI
import requests
from PIL import Image

from misc.ai.chat import Chat

openai = OpenAI()
chat = Chat(client=openai)
output_directory = "output"
num_prompts = 5
convert_svg = True

# Ensure the output directory exists
os.makedirs(output_directory, exist_ok=True)


def generate_sticker_prompts():
    return (
        chat.system("You are an expert graphic design assitant.")
        .user(
            "Generate a creative idea for a specifid sticker design of at least 5 sentences."
        )
        .text()
    )


def generate_image(prompt):
    response = openai.images.generate(
        model="dall-e-3", prompt=prompt, quality="hd", n=1, size="1024x1024"
    )
    url = response.data[0].url
    assert url is not None
    image_data = requests.get(url).content
    return Image.open(io.BytesIO(image_data))


def remove_background(image):
    output = io.BytesIO()
    image.save(output, format="PNG")
    response = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": output.getvalue()},
        data={"size": "auto"},
        headers={"X-Api-Key": remove_bg_api_key},
    )
    if response.status_code == requests.codes.ok:
        return Image.open(io.BytesIO(response.content))
    else:
        response.raise_for_status()


def convert_to_svg(image):
    import cairosvg

    output = io.BytesIO()
    image.save(output, format="PNG")
    png_data = output.getvalue()
    svg_data = cairosvg.png2svg(bytestring=png_data)
    return svg_data


def save_image(image, prompt, idx):
    base_filename = os.path.join(output_directory, f"sticker_{idx}")
    png_path = f"{base_filename}.png"
    image.save(png_path)

    if convert_to_svg:
        svg_data = convert_to_svg(image)
        svg_path = f"{base_filename}.svg"
        with open(svg_path, "wb") as svg_file:
            svg_file.write(svg_data)


def main():
    prompts = generate_sticker_prompts(num_prompts)
    for idx, prompt in enumerate(prompts):
        print(f"Generating image for prompt: {prompt}")
        image = generate_image(prompt)
        image_no_bg = remove_background(image)
        save_image(image_no_bg, prompt, idx)


if __name__ == "__main__":
    main()
