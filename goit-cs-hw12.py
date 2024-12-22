from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from multiprocessing import Process
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

import mimetypes
import json
import urllib.parse
import pathlib
import socket
import logging
import signal
import sys

uri = 'mongodb://mongodb:27012'

HTTPServer_Port = 3000
UDP_IP = "127.0.0.1"
UDP_Port = 5000


def send_data_to_socket(data):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server = UDP_IP, UDP_Port
    try:
        message = json.dumps(data).encode('utf-8')
        sock.sendto(message, server)
        logging.info(f"Data sent to {server}: {message}")
    except Exception as e:
        logging.error(f"Error sending data to {server}: {e}")
    finally:
        sock.close()


class HttpGetHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data)  # використовуйте JSON.parse для POST
            logging.info(f"Received POST data: {data}")
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response = {"status": "success", "message": "Data received"}
            self.wfile.write(json.dumps(response).encode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response = {"status": "error", "message": "Invalid JSON"}
            self.wfile.write(json.dumps(response).encode("utf-8"))

    def send_static(self, path):  # виправлено метод
        mime_type, _ = mimetypes.guess_type(str(path))
        try:
            with open(path, "rb") as file:
                content = file.read()
                self.send_response(200)
                self.send_header(
                    "Content-type", mime_type or "application/octet-stream")
                self.end_headers()
                self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>404 Not Found</h1>")


def run_http_server(server_class=HTTPServer, handler_class=HttpGetHandler):
    server_adress = ("0.0.0.0", HTTPServer_Port)
    http = server_class(server_adress, handler_class)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info(f"HTTP server starting on {
                 server_adress[0]}:{server_adress[1]}")

    def shutdown_server(signal_received, frame):
        logging.info("Shutting down HTTP server...")
        http.server_close()
        logging.info("Server successfully stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_server)
    signal.signal(signal.SIGTERM, shutdown_server)

    try:
        logging.info("Server is running. Press Ctrl+C to stop.")
        http.serve_forever()
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, stopping server.")
        http.server_close()
        logging.info("Server stopped.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        http.server_close()
        logging.info("Server stopped due to an error.")
    http.serve_forever()


def save_data(data):
    try:
        client = MongoClient(uri, server_api=ServerApi("1"))
        db = client.MY_CHAT
        collection = db.user_messages
        data_parse = urllib.parse.unquote_plus(data.decode())
        parsed_dict = dict(urllib.parse.parse_qsl(data_parse))

        document = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "username": parsed_dict.get("username", "Unknown"),
            "message": parsed_dict.get("message", "No message")
        }

        collection.insert_one(document)
        logging.info("Data saved to MongoDB successfully.")
    except Exception as e:
        logging.error(f"Failed to save data to MongoDB: {e}", exc_info=True)
    finally:
        client.close()


def run_socket_server(ip, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server = ip, port
        sock.bind(server)
        logging.info(f"Socket server started on {ip}:{port}")

        while True:
            data, addr = sock.recvfrom(1024)
            logging.info(f"Received data from {addr}: {data}")
            save_data(data)

    except Exception as e:
        logging.error(f"Error in socket server: {e}", exc_info=True)
    finally:
        sock.close()
        logging.info("Socket server shut down.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(threadName)s %(message)s")

    # Зробити 2 процеси для кожного з серверів
    http_server_process = Process(target=run_http_server)

    socket_server_process = Process(
        target=run_socket_server, args=(UDP_IP, UDP_Port))

    try:
        http_server_process.start()
        logging.info("HTTP server started.")

        socket_server_process.start()
        logging.info("Socket server started.")

        http_server_process.join()
        socket_server_process.join()

    except KeyboardInterrupt:
        logging.info("Shutting down servers...")

    finally:
        http_server_process.terminate()
        socket_server_process.terminate()
        http_server_process.join()
        socket_server_process.join()
        logging.info("Servers have been shut down.")
