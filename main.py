import hashlib
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


# ==============================
# CẤU HÌNH HỆ THỐNG
# ==============================

# Danh sách các node lưu trữ mô phỏng
NODES = ["node1", "node2", "node3"]

# Thư mục gốc của hệ thống
BASE_DIR = Path("storage_demo")

# Nơi chứa các node
NODES_DIR = BASE_DIR / "nodes"

# Ledger lưu thông tin file và hash gốc
LEDGER_PATH = BASE_DIR / "ledger.json"


# ==============================
# HÀM HỖ TRỢ
# ==============================

def ensure_system():
    """
    Tạo các thư mục cần thiết nếu chưa tồn tại.
    """
    NODES_DIR.mkdir(parents=True, exist_ok=True)

    for node in NODES:
        (NODES_DIR / node).mkdir(parents=True, exist_ok=True)


def load_json(path, default):
    """
    Đọc file JSON. Nếu file chưa tồn tại thì trả về giá trị mặc định.
    """
    path = Path(path)

    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    """
    Lưu dữ liệu ra file JSON.
    """
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sha256_file(path):
    """
    Tính mã băm SHA-256 của một file.
    Đọc file theo từng khối để không tốn RAM với file lớn.
    """
    hasher = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            hasher.update(chunk)

    return hasher.hexdigest()


def now_utc():
    """
    Lấy thời gian hiện tại dạng UTC.
    """
    return datetime.now(timezone.utc).isoformat()


def pretty(data):
    """
    In dữ liệu dạng JSON đẹp mắt.
    """
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ==============================
# CHỨC NĂNG CHÍNH
# ==============================

def upload_file(file_path, owner="demo"):
    """
    Lưu một file vào hệ thống phân tán mô phỏng.

    Các bước:
    1. Tính hash SHA-256 của file.
    2. Tạo file_id.
    3. Copy file sang từng node.
    4. Lưu manifest vào từng node.
    5. Lưu thông tin vào ledger.
    """

    ensure_system()

    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp: {file_path}")

    # Tính hash của file gốc
    file_hash = sha256_file(file_path)

    # Tạo ID cho file
    file_id = uuid.uuid4().hex[:12]

    timestamp = now_utc()

    # Đọc ledger hiện tại
    ledger = load_json(LEDGER_PATH, {"files": {}})

    # Lưu file vào từng node
    for node in NODES:
        node_dir = NODES_DIR / node

        # Đường dẫn file sẽ lưu trong node
        destination = node_dir / f"{file_id}.dat"

        # Copy file sang node
        shutil.copy2(file_path, destination)

        # Manifest của node
        manifest_path = node_dir / "manifest.json"
        manifest = load_json(manifest_path, {})

        manifest[file_id] = {
            "original_name": file_path.name,
            "sha256": file_hash,
            "owner": owner,
            "stored_at": timestamp
        }

        save_json(manifest_path, manifest)

    # Lưu thông tin vào ledger trung tâm
    ledger["files"][file_id] = {
        "original_name": file_path.name,
        "sha256": file_hash,
        "owner": owner,
        "uploaded_at": timestamp,
        "nodes": NODES.copy()
    }

    save_json(LEDGER_PATH, ledger)

    return {
        "file_id": file_id,
        "sha256": file_hash,
        "message": "Đã lưu file vào hệ thống phân tán mô phỏng."
    }


def verify_file(file_id):
    """
    Kiểm tra một file còn nguyên vẹn hay không.

    Các bước:
    1. Đọc ledger để lấy hash gốc.
    2. Kiểm tra file trên từng node.
    3. Tính lại hash thực tế.
    4. So sánh với manifest và ledger.
    5. Đưa ra kết luận.
    """

    ensure_system()

    ledger = load_json(LEDGER_PATH, {"files": {}})
    file_info = ledger["files"].get(file_id)

    if not file_info:
        return {
            "file_id": file_id,
            "status": "NOT_FOUND",
            "message": "Không tìm thấy file trong ledger."
        }

    expected_hash = file_info["sha256"]
    nodes = file_info.get("nodes", [])

    details = []
    ok_count = 0

    for node in nodes:
        manifest_path = NODES_DIR / node / "manifest.json"
        data_path = NODES_DIR / node / f"{file_id}.dat"

        manifest = load_json(manifest_path, {})
        manifest_entry = manifest.get(file_id)

        # Nếu node thiếu file hoặc thiếu manifest
        if not manifest_entry or not data_path.is_file():
            details.append({
                "node": node,
                "status": "MISSING",
                "message": "Không có dữ liệu hoặc manifest trên node này."
            })
            continue

        # Tính hash thực tế của file trên node
        actual_hash = sha256_file(data_path)

        # Hash được lưu trong manifest của node
        manifest_hash = manifest_entry.get("sha256")

        matches_manifest = actual_hash == manifest_hash
        matches_ledger = actual_hash == expected_hash

        node_ok = matches_manifest and matches_ledger

        if node_ok:
            ok_count += 1

        details.append({
            "node": node,
            "status": "OK" if node_ok else "MISMATCH",
            "actual_hash": actual_hash,
            "manifest_hash": manifest_hash,
            "matches_manifest": matches_manifest,
            "matches_ledger": matches_ledger
        })

    total_nodes = len(nodes)
    majority = total_nodes // 2 + 1

    # Kết luận
    if total_nodes > 0 and ok_count == total_nodes:
        status = "VALID"
        message = "File nguyên vẹn và khớp với tất cả node."

    elif ok_count >= majority:
        status = "PARTIALLY_VALID"
        message = "Đa số node hợp lệ, nhưng có node bị lỗi hoặc bị thay đổi."

    else:
        status = "INVALID"
        message = "Không đủ bằng chứng để kết luận file nguyên vẹn."

    return {
        "file_id": file_id,
        "expected_hash": expected_hash,
        "status": status,
        "message": message,
        "ok_nodes": ok_count,
        "total_nodes": total_nodes,
        "details": details
    }


def list_files():
    """
    Liệt kê các file đã được lưu trong ledger.
    """
    ledger = load_json(LEDGER_PATH, {"files": {}})
    return ledger["files"]


def tamper_node_file(file_id, node="node1"):
    """
    Hàm này chỉ dùng để mô phỏng tấn công.

    Nó sẽ ghi thêm dữ liệu vào file trên một node,
    làm cho hash của node đó thay đổi.
    """

    ensure_system()

    target = NODES_DIR / node / f"{file_id}.dat"

    if not target.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy file cần mô phỏng tấn công trên {node}."
        )

    with open(target, "ab") as f:
        f.write(b"[bi sua trai phep]")

    return {
        "message": f"Đã mô phỏng chỉnh sửa file trên {node}.",
        "target": str(target)
    }


# ==============================
# GIAO DIỆN DÒNG LỆNH
# ==============================

if __name__ == "__main__":
    help_text = """
Cách dùng:
  python main.py upload <duong_dan_file> [owner]
  python main.py verify <file_id>
  python main.py list
  python main.py tamper <file_id> [node]

Ví dụ:
  python main.py upload test.txt Alice
  python main.py verify abc123
  python main.py tamper abc123 node1
"""

    if len(sys.argv) < 2:
        print(help_text)
        sys.exit(0)

    command = sys.argv[1]

    if command == "upload":
        if len(sys.argv) < 3:
            print("Thiếu đường dẫn file.")
            print("Ví dụ: python main.py upload test.txt Alice")
            sys.exit(1)

        file_path = sys.argv[2]
        owner = sys.argv[3] if len(sys.argv) > 3 else "demo"

        pretty(upload_file(file_path, owner))

    elif command == "verify":
        if len(sys.argv) < 3:
            print("Thiếu file_id.")
            print("Ví dụ: python main.py verify <file_id>")
            sys.exit(1)

        pretty(verify_file(sys.argv[2]))

    elif command == "list":
        pretty(list_files())

    elif command == "tamper":
        if len(sys.argv) < 3:
            print("Thiếu file_id.")
            print("Ví dụ: python main.py tamper <file_id> node1")
            sys.exit(1)

        file_id = sys.argv[2]
        node = sys.argv[3] if len(sys.argv) > 3 else "node1"

        pretty(tamper_node_file(file_id, node))

    else:
        print("Lệnh không hợp lệ.")
        print(help_text)