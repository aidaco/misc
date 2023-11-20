import sys
from pathlib import Path
from typing import Literal
from time import time_ns
from datetime import datetime
import json

from openai import OpenAI
import urllib.request


key = open('/home/aidan/.secrets/openai-api-key').read().strip()
client = OpenAI(api_key=key)

OUTDIR = Path('results')


def generate_image(
    prompt: str,
    output_dir: Path,
    model: Literal['dall-e-3',  'dall-e-2'] = 'dall-e-3',
    size: Literal['1024x1024', '1792x1024', '1024x1792'] = '1792x1024',
    quality: Literal['standard', 'hd'] = 'hd',
    style: Literal['vivid', 'natural'] = 'vivid',
    suffix: str = 'strictly contained within the image boundaries',
):

    tag = f'{time_ns():x}'
    if suffix:
        prompt = f'{prompt} {suffix}'
    parameters = dict(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
    )

    url = client.images.generate(
        **parameters,
        n=1
    ).data[0].url
    with urllib.request.urlopen(url) as remote:
        with (output_dir/f'{tag}.png').open('wb') as local:
            local.write(remote.read())
    with (output_dir/f'{tag}.txt').open('w') as prompt_store:
        prompt_store.writelines([
            '{',
            *(
                '\t'f"'{k}': '{v}'" for k, v in parameters.items()
            ),
            '}',
        ])


def find_strs(o):
    match o:
        case str():
            yield o
        case dict():
            for v in o.values():
                yield from find_strs(v)
        case list():
            for e in o:
                yield from find_strs(e)
        case _:
            print(f'unable to process {o}')


def generate_variations(prompt: str) -> list[str]:
    response = client.chat.completions.create(
      model="gpt-4-1106-preview",
      messages=[
        {"role": "system", "content": "You are a helpful assistant that generates more optimized and intricately detailed suggestions for prompts to be given to an AI image generation model. Please responde only with a JSON object with a 'suggested_prompts' key holding an array with 5 suggested prompts of 100 to 200 words."},
        {"role": "user", "content": prompt},
      ],
      n=1,
      response_format={"type": "json_object"},
    ).choices[0].message.content

    return [s for s in find_strs(json.loads(response)) if moderate_prompt(s)]


def moderate_prompt(prompt: str) -> bool:
    response = client.moderations.create(input="Sample text goes here.").results[0]
    return not response.flagged


def generate_image_variations(prompt: str):
    if not moderate_prompt(prompt):
        raise ValueError('bad prompt')
    tag = f'{datetime.now():%Y-%m-%d %H-%M-%S}'
    print(f'TAG: {tag}')

    prompts = [
        prompt,
        *generate_variations(prompt)
    ]
    
    prompt_dir = OUTDIR / tag
    prompt_dir.mkdir(parents=True, exist_ok=False)
    for p in prompts:
        generate_image(p, prompt_dir)
        print('"', p, '"')


if __name__ == '__main__':
    match sys.argv[1:]:
        case [arg]:
            prompt = arg.strip()
        case [*args]:
            prompt = ' '.join(args).strip()
    generate_image_variations(prompt)
