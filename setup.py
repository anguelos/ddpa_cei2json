from setuptools import setup, find_packages

setup(
    name="ddpa_cei2json",
    version="0.1.0",
    packages=find_packages(where='src'),
    package_dir={"": "src"},
    include_package_data=True,  # important for templates/static
    install_requires=[
        "Flask>=2.0", "lxml>=4.6", "beautifulsoup4>=4.9", "tqdm>=4.60", "fargv>=0.1.3", "flask",
    ],
    entry_points={
        "console_scripts": [
            # command-name = package.module:function
            "ddp_cei2json_serve = ddp_cei.cei2json_serve:serve_cli_main",
        ],
    },
)
