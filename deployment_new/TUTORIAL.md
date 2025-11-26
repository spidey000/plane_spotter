# Deployment Tutorial for Dummies

This guide will walk you through setting up your VPS and deploying the Twitter Spotter application step-by-step.

## Prerequisites

- A VPS (Virtual Private Server) with **Ubuntu** or **Debian** installed.
- Access to a terminal on your local computer (PowerShell on Windows, Terminal on Mac/Linux).
- `git` installed on your local computer.

---

## Step 1: Generate SSH Keys (If you don't have them)

SSH keys allow you to log in to your server without typing a password every time.

1.  **Open PowerShell** on your local computer.
2.  Run the following command:
    ```powershell
    ssh-keygen -t ed25519 -C "your_email@example.com"
    ```
3.  Press **Enter** to accept the default file location.
4.  Press **Enter** twice to skip setting a passphrase (for easier automation).

## Step 2: Copy SSH Key to Your VPS

1.  Run this command (replace `root` and `your_vps_ip` with your actual details):
    ```powershell
    type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@your_vps_ip "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
    ```
2.  **Test it**: Try logging in:
    ```powershell
    ssh root@your_vps_ip
    ```
    You should be logged in *without* being asked for a password. Type `exit` to return to your local machine.

---

## Step 3: Install Docker on Your VPS

1.  Log in to your VPS: `ssh root@your_vps_ip`
2.  Run this single command to install Docker and Docker Compose:
    ```bash
    curl -fsSL https://get.docker.com | sh
    ```
3.  Verify it works:
    ```bash
    docker --version
    docker compose version
    ```
4.  Type `exit` to disconnect.

---

## Step 4: Prepare Deployment Files

1.  Go to the `deployment_new` folder in your project.
2.  **Rename** `deploy.txt` to `deploy.sh`:
    ```powershell
    mv deploy.txt deploy.sh
    ```
3.  **Rename** `env.example` to `.env`:
    ```powershell
    mv env.example .env
    ```
4.  **Edit `.env`**: Open it and fill in your real API keys.

---

## Step 5: Run the Deployment

1.  Open PowerShell in your project root.
2.  Run the deployment script (replace with your VPS IP):
    ```powershell
    $env:REMOTE_HOST="your_vps_ip"; sh deployment_new/deploy.sh
    ```
    *Note: If you don't have `sh` (Git Bash) in your path, you might need to run it from Git Bash or install it.*

---

## Troubleshooting

- **Permission Denied**: If the script says "Permission denied", try running `chmod +x deployment_new/deploy.sh` (if you are on Linux/Mac/Git Bash).
- **Docker not found**: Ensure you installed Docker on the VPS (Step 3).
