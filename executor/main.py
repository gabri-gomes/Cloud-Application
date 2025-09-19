from flask import Flask, request, jsonify
import os
import subprocess
import uuid

app = Flask(__name__)

@app.route("/execute", methods=["POST"])
def execute_code():
    file = request.files.get("file")
    language = request.form.get("language", "python")
    input_file = request.files.get("input")  # ← input.txt opcional

    if not file:
        return jsonify({"error": "Nenhum ficheiro enviado."}), 400

    file_ext = language.lower()
    file_uuid = uuid.uuid4().hex
    filename = f"/tmp/{file_uuid}.{file_ext}"
    file.save(filename)

    input_path = None
    if input_file:
        input_path = f"/tmp/{file_uuid}_input.txt"
        input_file.save(input_path)

    output = ""

    try:
        if language in ["py", "python"]:
            if input_path:
                with open(input_path, "rb") as f_in:
                    result = subprocess.run(["python3", filename], stdin=f_in, capture_output=True, text=True, timeout=10)
            else:
                result = subprocess.run(["python3", filename], capture_output=True, text=True, timeout=10)
            output = result.stdout + result.stderr

        elif language in ["cpp", "c++"]:
            exe_file = f"/tmp/{file_uuid}_cpp.out"
            compile_cmd = ["g++", filename, "-o", exe_file]
            compile = subprocess.run(compile_cmd, capture_output=True, text=True)
            if compile.returncode != 0:
                output = " Erro de compilação:\n" + compile.stderr
            else:
                with open(input_path, "rb") if input_path else subprocess.DEVNULL as f_in:
                    run = subprocess.run([exe_file], stdin=f_in if input_path else None, capture_output=True, text=True, timeout=10)
                output = run.stdout + run.stderr
                os.remove(exe_file)

        elif language in ["js", "javascript"]:
            if input_path:
                with open(input_path, "rb") as f_in:
                    result = subprocess.run(["node", filename], stdin=f_in, capture_output=True, text=True, timeout=10)
            else:
                result = subprocess.run(["node", filename], capture_output=True, text=True, timeout=10)
            output = result.stdout + result.stderr

        elif language in ["rs", "rust"]:
            exe_file = f"/tmp/{file_uuid}_rs.out"
            compile_cmd = ["rustc", filename, "-o", exe_file]
            compile = subprocess.run(compile_cmd, capture_output=True, text=True)
            if compile.returncode != 0:
                output = " Erro de compilação:\n" + compile.stderr
            else:
                with open(input_path, "rb") if input_path else subprocess.DEVNULL as f_in:
                    run = subprocess.run([exe_file], stdin=f_in if input_path else None, capture_output=True, text=True, timeout=10)
                output = run.stdout + run.stderr
                os.remove(exe_file)

        else:
            return jsonify({"error": "Linguagem não suportada."}), 400

    except subprocess.TimeoutExpired:
        output = " Tempo limite excedido."
    except Exception as e:
        output = f" Erro inesperado: {str(e)}"

    os.remove(filename)
    if input_path:
        os.remove(input_path)

    return jsonify({"output": output})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
