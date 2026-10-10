from flask import Flask, request, jsonify
import boto3
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Initialize AWS S3 client (credentials should be provided via environment variables or IAM role)
s3 = boto3.client(
    's3',
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)
S3_BUCKET = os.getenv('S3_BUCKET')

# Initialize Postgres connection (provide via environment variables)
POSTGRES_DSN = os.getenv('POSTGRES_DSN')

def get_pg_connection():
    return psycopg2.connect(POSTGRES_DSN)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    # Upload to S3
    s3_key = f"uploads/{file.filename}"
    try:
        s3.upload_fileobj(file, S3_BUCKET, s3_key)
    except Exception as e:
        return jsonify({'error': f'S3 upload failed: {str(e)}'}), 500
    # Record activity in Postgres
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user_activity (filename, s3_key, uploaded_at) VALUES (%s, %s, NOW())",
            (file.filename, s3_key)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({'error': f'Postgres insert failed: {str(e)}'}), 500
    return jsonify({'message': 'File uploaded successfully', 's3_key': s3_key}), 200

if __name__ == '__main__':
    # For Docker use, bind to 0.0.0.0
    app.run(host='0.0.0.0', port=5000)

