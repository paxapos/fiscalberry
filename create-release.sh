#!/bin/bash
VERSION=${1:-$(date +%Y.%m.%d)}
TAG="v$VERSION"
git tag -a "$TAG" -m "Release $TAG"
git push origin "$TAG"
echo "✅ Release $TAG creado. GitHub Actions compilará automáticamente."
