"""
TEAMSYNC — Shared Configuration
Central store for URLs, endpoints, headers, and test credentials.
Used by both UI and API tests — never define test data in test files.
"""

import os

# ── Base URL ──────────────────────────────────────────────────
BASE_URL      = "http://frontdms-teamsync.apps.lab.ocp.lan"
LOGIN_PAGE_URL = f"{BASE_URL}/"

# ── Endpoints ─────────────────────────────────────────────────
ENDPOINTS = {
    "login"          : f"{BASE_URL}/api/tenants/public/users/login",
    "logout"         : f"{BASE_URL}/api/tenants/logout",
    "upload"         : f"{BASE_URL}/api/dmsUploadModule/api/upload",
    "file_open"      : f"{BASE_URL}/api/dms_service_LM/api/getFileOpenURL",
    "download"       : f"{BASE_URL}/api/dms_service_LM/api/download",
    "operations"     : f"{BASE_URL}/api/operationModule/api/operations",
    "create_docx"    : f"{BASE_URL}/api/dms_service_LM/api/createNewDocx",
    "move_file"      : f"{BASE_URL}/api/dms_service_LM/api/moveFile",
    "move_paths"     : f"{BASE_URL}/api/dms_service_LM/api/movePaths",
}

# ── Upload config ─────────────────────────────────────────────
# Absolute path avoids Windows forward-slash/backslash mismatch
DATA_SET_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "Data Set", "Document_with_all_extension")
)
UPLOAD_FOLDER_PATH = os.path.join(DATA_SET_PATH, "Upload folder")

# Actual filenames in the Data Set folder — used by upload tests
UPLOAD_FILES = {
    "png"    : "image (3).png",
    "jpg"    : "file_example_JPG_2500kB.jpg",
    "pdf"    : "A_Brief_Introduction_To_AI.pdf",
    "doc"    : "sample (1).doc",
    "docx"   : "India_Overview.docx",
    "test_docx"  : "test.docx",
    "xls"    : "tests-example.xls",
    "xlsx"   : "FlyingDataAnalytics.xlsx",
    "zip"    : "test_small.zip",
    "html"   : "sample1.html",
    "svg"    : "sample_640×426.svg",
    "gif"    : "eglite.gif",
    "bmp"    : "lena_gray.bmp",
    "tif"    : "image.tif",
    "webp"   : "file_example_WEBP_1500kB.webp",
    "mp3"    : "freesound_community-water-dripping-ogg-format-70421.mp3",
    "mp4"    : "6 Qualities That Make a Great Leader __ APJ Abdul Kalam (2).mp4",
    "avi"    : "drop.avi",
    "mkv"    : "sample-1.mkv",
    "mov"    : "sample_1280x720.mov",
    "webm"   : "lion-sample.webm",
    "wmv"    : "1MB_1080P_THETESTDATA.COM_WMV.wmv",
    "flv"    : "1MB_480P_THETESTDATA.COM_flv.flv",
    "3gpp"   : "record20210310234119.3gpp",
    "7z"     : "7z2600-extra.7z",
    "gz"     : "sample-1.gz",
    "tar"    : "External_test_data.tar",
    "json"   : "DMScollection.json",
    "xml"    : "India_Overview.xml",
    "rtf"    : "sample.rtf",
    "txt"    : "RainP_water_10000.txt",
    "ppt"    : "sample3.ppt",
    "pptx"   : "Extlst-test.pptx",
    "exe"    : "Git-2.53.0.2-64-bit.exe",
    "m4a"    : "example.m4a",
    "aac"    : "AAC - 11SECS - SMALL.aac",
    "bat"    : "test_security.bat",
    "js"     : "test_security.js",
    "abc"    : "test_security.abc",
    "noext"       : "test_security_noext",
    "empty"       : "0kb.pdf",
    "over_limit"  : "480MB (1).pdf",
    "protected_xlsx" : "protected.xlsx",
    "large_50mb"  : "large_50mb.bin",
}

UPLOAD_EXTRA_HEADERS = {
    "Type"                  : "File Upload",
    "username"              : "ankit@gmail.com",
    "generatingAiTheme"     : "true",
    "metadataType"          : "AiMetaDataExtraction",
    "textRecognitionMethod" : "OCR",
    "uploadCount"           : "0",
}

# ── Headers ───────────────────────────────────────────────────
DEFAULT_HEADERS = {
    "appName": "TeamSync",
    "Origin" : BASE_URL,
}

# ── Valid credentials ─────────────────────────────────────────
VALID_USERNAME           = "ankit@gmail.com"
VALID_PASSWORD           = "test"
VALID_PASSWORD_ENCRYPTED = VALID_PASSWORD      # same value — browser sends plain text

# ── Invalid / negative test credentials ──────────────────────
WRONG_PASSWORD           = "WrongPass@999"
WRONG_PASSWORD_ENCRYPTED = "test1"
WRONG_USERNAME           = "invaliduser@test.com"
DISABLED_USER            = "pratibha@appolo.com"
INVALID_EMAIL            = "abc@"
