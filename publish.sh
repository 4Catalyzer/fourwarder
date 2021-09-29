set -eu

poetry version $1
VERSION_NUMBER=v$(poetry version -s)

rm -rf ./dist/
poetry build
poetry publish

git add pyproject.toml
git commit -m "release fourwarder"
git tag $VERSION_NUMBER
