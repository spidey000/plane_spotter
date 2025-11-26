@echo off
REM Twitter Spotter v4 - Docker Build Script for Windows
REM This script builds the Docker image with automatic versioning

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Docker is not installed or not in PATH
    exit /b 1
)

REM Check if Git Bash is available
where bash >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Git Bash is not installed or not in PATH
    echo Please install Git for Windows which includes Git Bash
    exit /b 1
)

REM Run the bash script with all arguments
bash build-docker.sh %*