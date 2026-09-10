const fs = require('fs');
const path = require('path');

const target = path.join(__dirname, '..', 'node_modules', 'react-native-svg', 'src', 'xml.ts');
const content = `export * from './xml.tsx';\nexport { default } from './xml.tsx';\n`;

try {
  if (fs.existsSync(path.dirname(target)) && !fs.existsSync(target)) {
    fs.writeFileSync(target, content, 'utf8');
    console.log('[patch-svg] Successfully created react-native-svg/src/xml.ts bridge');
  }
} catch (e) {
  console.warn('[patch-svg] Failed to apply react-native-svg patch:', e.message);
}
