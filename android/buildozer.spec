[app]

title = PyScreen Viewer
package.name = pyscreen
package.domain = com.pyscreen
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0.0

requirements = python3,kivy,pillow,websocket-client

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 31
android.minapi = 21
android.ndk = 25b
android.archs = armeabi-v7a
android.accept_sdk_license = True

fullscreen = 0
orientation = portrait
icon.filename = %(source.dir)s/icon.png

android.enable_androidx = True

log_level = 2
