from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="dump_github",
    version="0.1.0",
    author="core2002",
    author_email="core2002@aliyun.com",
    description="A small example package",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/core2002/dump_github",
    packages=find_packages(),
    license="MIT",
    install_requires=[
        "argparse",
        "requests"
    ],
    entry_points={
        "console_scripts":[
            "dump_github = dump_github:main"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)