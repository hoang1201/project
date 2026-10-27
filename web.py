from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from pathlib import Path

from main import upload_file, verify_file, list_files


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)


@app.route("/")
def home():
    return """
    <h2>Hệ thống lưu trữ phân tán mini</h2>

    <h3>Upload file</h3>
    <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file" required>
        <br><br>
        <input type="text" name="owner" placeholder="Tên chủ sở hữu">
        <br><br>
        <button type="submit">Upload</button>
    </form>
    """


@app.post("/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Chưa chọn file"}), 400

    f = request.files["file"]

    safe_name = secure_filename(f.filename)

    if not safe_name:
        safe_name = "uploaded_file"

    save_path = UPLOAD_DIR / safe_name

    f.save(save_path)

    owner = request.form.get("owner", "anonymous")

    result = upload_file(save_path, owner)

    return jsonify(result)


@app.route("/verify/<file_id>")
def verify(file_id):
    return jsonify(verify_file(file_id))


@app.route("/files")
def files():
    return jsonify(list_files())


if __name__ == "__main__":
    app.run(debug=True)