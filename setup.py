"""Packaging for ros2-ai-debugger.

Metadata lives here (not in pyproject.toml's [project] table) because the
setuptools shipped with Ubuntu 22.04 / ROS 2 Humble (59.x) predates PEP 621,
and colcon's ament_python builds use the system setuptools.
"""
from setuptools import find_packages, setup

package_name = "ros2_ai_debugger"

setup(
    name=package_name,
    version="0.1.0",
    description="AI-assisted diagnostics and troubleshooting for ROS 2 systems.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    license="Apache-2.0",
    python_requires=">=3.10",
    packages=find_packages(exclude=["tests", "tests.*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    extras_require={
        "claude": ["anthropic>=0.40"],
        "openai": ["openai>=1.0"],
        "gemini": ["google-genai>=1.0"],
        "dev": ["pytest>=7", "ruff"],
    },
    zip_safe=True,
    entry_points={
        "console_scripts": ["ros2-ai = ros2_ai_debugger.cli.main:main"],
        # Registers `ros2 ai ...` with the ros2cli command extension point.
        "ros2cli.command": ["ai = ros2_ai_debugger.cli.ros2_command:AICommand"],
    },
)
