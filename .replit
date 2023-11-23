entrypoint = "main.py"
modules = ["python-3.10:v18-20230807-322e88b"]

hidden = [".pythonlibs"]

[nix]
channel = "stable-23_05"

[unitTest]
language = "python3"

[deployment]
run = ["python3", "main.py"]
deploymentTarget = "cloudrun"