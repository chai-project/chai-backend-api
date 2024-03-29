from setuptools import setup

# Note that on M1 macs (and any mac with macOS Monterey installed) the installation of bjoern causes problems.
# To overcome these and get bjoern to install you need to:
#  1. install libev using homebrew
#  2. install bjoern manually using pip3 install --global-option=build_ext --global-option="-I/opt/homebrew/include" --global-option="-L/opt/homebrew/lib" bjoern  # noqa
# This ensures that the installation proceeds as expected by pointing to the right installation location of libev .

setup(
    name="chai-api",
    packages=["chai_api"],
    version="0.2.0",
    description="API server to access the CHAI backend.",
    author="Kim Bauters",
    author_email="kim.bauters@bristol.ac.uk",
    license="Protected",
    install_requires=["pendulum",  # handle datetime instances with ease
                      "dacite",  # convert dictionaries to dataclass instances
                      "ujson",  # fast JSON encoder and decoder
                      "falcon",  # fast web framework
                      "click",  # easy decorator style command line interface
                      "falcon_auth",  # simple authentication middleware for falcon
                      "pg8000",  # pure Python PostgreSQL database adapter
                      "sqlalchemy",  # ORM for database access
                      "falcon_sqla",  # SQL session middleware for falcon
                      "tomli",  # TOML configuration file parser
                      "pushover_complete",  # simple instant notifications service
                      "requests",  # handle API requests
                      # "chai-data-sources",  # Netatmo data sources for CHAI
                      ],
    extras_require={
        "compat": ["cheroot", "pylint", "perflint"],  # pure Python WSGI server
        "speed": ["bjoern"],  # fast WSGI server
    },
    classifiers=[],
    include_package_data=True,
    platforms="any",

)
