const fs = require('fs');
const { PNG } = require('pngjs');
const glob = require('glob');

function createEmptyPng(width, height, filePath) {
  const png = new PNG({ width, height });
  for (let y = 0; y < png.height; y++) {
    for (let x = 0; x < png.width; x++) {
      const idx = (png.width * y + x) << 2;
      png.data[idx] = 255;
      png.data[idx + 1] = 255;
      png.data[idx + 2] = 255;
      png.data[idx + 3] = 255;
    }
  }
  png.pack().pipe(fs.createWriteStream(filePath));
}

glob.sync('android/app/src/main/res/mipmap-*').forEach(dir => {
  createEmptyPng(108, 108, `${dir}/ic_launcher_foreground.png`);
});
