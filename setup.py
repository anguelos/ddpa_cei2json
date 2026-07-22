from setuptools import setup, find_packages

version = {}
with open("src/ddp_cei/version.py") as f:
    exec(f.read(), version)

setup(
    name="ddpa_cei2json",
    version=version["__version__"],
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    include_package_data=True,  # important for templates/static
    install_requires=[
        "Flask>=2.0",
        "lxml>=4.6",
        "beautifulsoup4>=4.9",
        "tqdm>=4.60",
        "fargv>=1.3.3",
        "numpy",
        "pylelemmatize",
        "anyascii",
        # didip_util is the pip distribution providing the fsdb, ddp_util and
        # ddp_microservices modules the offline/serve CLIs import.
        "didip_util",
    ],
    entry_points={
        "console_scripts": [
            # command-name = package.module:function
            "ddpa_cei2json_offline = ddp_cei.cei2json_offline:main",
            "ddpa_cei2json_serve = ddp_cei.cei2json_serve:serve_cli_main",
        ],
    },
)
