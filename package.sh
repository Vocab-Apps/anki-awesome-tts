#!/bin/bash

set -eoux pipefail

# exit if argument is not passed in
if [ -z "$2" ]; then
  echo "Please pass major, minor or patch, and release notes"
  exit 1
fi

BUMP_TYPE=$1 # major, minor or patch
# check that the bump type is valid
if [ "$BUMP_TYPE" != "major" ] && [ "$BUMP_TYPE" != "minor" ] && [ "$BUMP_TYPE" != "patch" ]; then
  echo "Please pass major, minor or patch"
  exit 1
fi

NEW_VERSION=`bump2version --list ${BUMP_TYPE} | grep new_version | sed -r s,"^.*=",,`
# push to upstream
git push
git push --tags

VERSION_NUMBER=${NEW_VERSION}

# create .addon file
# remove meta.json, which contains private key
rm -f meta.json
rm -rf __pycache__
rm -f user_files/*.mp3
rm -f user_files/*.ogg
rm -rvf htmlcov/

ADDON_FILENAME=${HOME}/anki-addons-releases/anki-awesome-tts-${VERSION_NUMBER}.ankiaddon
zip -9 "${ADDON_FILENAME}" \
    awesometts/blank.mp3 \
    awesometts/LICENSE.txt \
    awesometts/*.py \
    awesometts/gui/*.py \
    awesometts/gui/icons/*.png \
    awesometts/service/*.py \
    awesometts/service/*.js \
    user_files/README.txt \
    __init__.py \
    manifest.json

# sync 
rclone sync ~/anki-addons-releases/ dropbox:Anki/anki-addons-releases/

# create github release
RELEASE_NOTES=$2
gh release create v${VERSION_NUMBER} ${ADDON_FILENAME} --title "AwesomeTTS v${VERSION_NUMBER}" --notes "${RELEASE_NOTES}"

# if you need to undo a release:
# git tag -d v0.2
# git push --delete origin v0.2
