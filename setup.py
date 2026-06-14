from setuptools import setup, find_packages

setup(
    name="bulk-email-validator",
    version="1.0.0",
    description="High-performance bulk email validator with syntax, MX, and SMTP checks",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "email-validator",
        "dnspython",
        "tqdm",
    ],
    entry_points={
        "console_scripts": [
            "email-validator=validator:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
