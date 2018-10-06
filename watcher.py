import sys
import os
import platform
import time
import base64
import magic
import json
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from img_process import extract_text_from_image, extract_text_from_pdf,\
                        pdf_page_to_image
from settings import PATH, SERVER
from api_token import get_token_suffix

'''
2018-09-24 JRK
This program was created to upload files from a folder specified in the
PATH variable to Joplin. The following resource was helpful in figuring out
the logic for Watchdog:
https://stackoverflow.com/questions/18599339/python-watchdog-monitoring-file-for-changes

Tested with the following extensions:
.md
.txt
.pdf
.png
.jpg

Caveat
Uploader only triggered upon new file creation, not modification
'''


TOKEN = get_token_suffix()


class MyHandler(FileSystemEventHandler):
    def on_created(self, event):
        print(event.event_type + " -- " + event.src_path)
        filename, ext = os.path.splitext(event.src_path)
        if ext != '.tmp':
            for i in range(10):
                if os.path.getsize(event.src_path) < 1:
                    if i == 9:
                        print("timeout error, file zero bytes")
                        return False
                    time.sleep(5)
                else:
                    upload(event.src_path)
                    return True
        else:
            print("Detected temp file. Temp files are ignored.")


# Set working Directory
def set_working_directory():
    if os.getcwd() != os.chdir(os.path.dirname(os.path.realpath(__file__))):
        os.chdir(os.path.dirname(os.path.realpath(__file__)))


def read_text_note(filename):
    with open(filename, 'r') as myfile:
        text = myfile.read()
        print(text)
    return text


def create_resource(filename):
    basefile = os.path.basename(filename)
    title = os.path.splitext(basefile)[0]
    files = {
        'data': (json.dumps(filename), open(filename, 'rb')),
        'props': (None, '{{"title":"{}", "filename":"{}"}}'.format(title,
                                                                   basefile))
    }
    response = requests.post(SERVER + '/resources' + TOKEN, files=files)
    print(response.json())
    return response.json()


def delete_resource(resource_id):
    apitext = SERVER + '/resources/' + resource_id + TOKEN
    response = requests.delete(apitext)
    return response


def get_resource(resource_id):
    apitext = SERVER + '/resources/' + resource_id + TOKEN
    response = requests.get(apitext)
    return response


def encode_image(filename, datatype):
    encoded = base64.b64encode(open(filename, "rb").read())
    img = "data:{};base64,{}".format(datatype, encoded.decode())
    return img


def set_json_string(title, body, img=None):
    if img is None:
        return '{{ "title": {}, "body": {} }}'\
            .format(json.dumps(title), json.dumps(body))
    else:
        return '{{ "title": "{}", "body": {}, "image_data_url": "{}" }}'\
            .format(title, json.dumps(body), img)


def upload(filename):
    basefile = os.path.basename(filename)
    title = os.path.splitext(basefile)[0]
    body = basefile + " uploaded from " + platform.node() + "\n"
    mime = magic.Magic(mime=True)
    datatype = mime.from_file(filename)
    if datatype == "text/plain":
        body += read_text_note(filename)
        values = set_json_string(title, body)
    elif datatype[:5] == "image":
        img = encode_image(filename, datatype)
        body += extract_text_from_image(filename)
        values = set_json_string(title, body, img)
    else:
        response = create_resource(filename)
        body += '[](:/{})'.format(response['id'])
        values = set_json_string(title, body)
        if response['file_extension'] == 'pdf':
            # Special handling for PDFs
            body += extract_text_from_pdf(filename)
            previewfile = pdf_page_to_image(filename)
            img = encode_image(previewfile, "image/png")
            print(len(body))
            if len(body) <= 100:
                # if embedded PDF text is minimal or does not exist,
                # run OCR the preview file
                body += extract_text_from_image(previewfile)
            values = set_json_string(title, body, img)

    response = requests.post(SERVER + '/notes' + TOKEN, data=values)
    print(response)
    print(response.text)
    print(response.json())


if __name__ == "__main__":
    set_working_directory()
    event_handler = MyHandler()
    observer = Observer()
    observer.schedule(event_handler, path=PATH, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
