"""Deploy the assembled Space (space_build/) to Hugging Face.

Run AFTER `huggingface-cli login` (a write token):
    python space/deploy.py twelveswaras/twelveswaras
or, to deploy under your personal account first:
    python space/deploy.py <your-hf-username>/twelveswaras

Uses huggingface_hub.upload_folder, which LFS-handles the model automatically.
"""
import sys

from huggingface_hub import HfApi, create_repo

if len(sys.argv) != 2 or "/" not in sys.argv[1]:
    raise SystemExit("usage: python space/deploy.py <owner>/<space-name>")

repo_id = sys.argv[1]
create_repo(repo_id, repo_type="space", space_sdk="gradio", exist_ok=True)
HfApi().upload_folder(folder_path="space_build", repo_id=repo_id, repo_type="space",
                      commit_message="Deploy twelveswaras recognizer")
print(f"Deployed: https://huggingface.co/spaces/{repo_id}")
print(f"Live (after build): https://{repo_id.replace('/', '-')}.hf.space")
