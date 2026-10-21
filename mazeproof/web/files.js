// Kept in sync with workspace.MAX_PROJECT_BYTES by the file-contract tests.
export const MAX_PROJECT_BYTES = 128 * 1024 * 1024;
export const MAX_BUNDLE_BYTES = 128 * 1024 * 1024;
export const PROJECT_SIZE_MESSAGE =
  "作業ファイルが128MiBを超えるため、保存できません。現在の作業は残っています。画面を閉じず、原画像や修正した構造・レポートを別に保管してください。";

export function projectBlob(project) {
  // The same compact representation is sent back on restore. Pretty-printing
  // large wall/route arrays can make a readable input impossible to reopen.
  const blob = new Blob([JSON.stringify(project)], {
    type: "application/json",
  });
  if (blob.size > MAX_PROJECT_BYTES) throw new Error(PROJECT_SIZE_MESSAGE);
  return blob;
}

// Native JSON.parse discards duplicate members before the server can reject
// them. Validate imported files before replacing the current workspace.
export function parseStrictJSON(text) {
  let position = 0;
  const invalid = () => {
    throw new Error(
      "JSONの形式が正しくありません。元のファイルを確認してください。",
    );
  };
  const whitespace = () => {
    while (position < text.length && " \t\r\n".includes(text[position]))
      position++;
  };
  const string = () => {
    if (text[position] !== '"') invalid();
    const start = position++;
    while (position < text.length) {
      const c = text[position++];
      if (c === "\\") position++;
      else if (c === '"') {
        try {
          return JSON.parse(text.slice(start, position));
        } catch {
          invalid();
        }
      }
    }
    invalid();
  };
  const value = (depth) => {
    if (depth > 100)
      throw new Error(
        "JSONの入れ子が深すぎます。元のファイルを確認してください。",
      );
    whitespace();
    const c = text[position];
    if (c === '"') return string();
    if (c === "{" || c === "[") {
      const object = c === "{";
      const end = object ? "}" : "]";
      const result = object ? {} : [];
      const keys = new Set();
      position++;
      whitespace();
      if (text[position] === end) {
        position++;
        return result;
      }
      while (position < text.length) {
        whitespace();
        let key;
        if (object) {
          key = string();
          if (keys.has(key))
            throw new Error(
              "JSONに同じ項目名が重複しています。元のファイルを修正してください。",
            );
          keys.add(key);
          whitespace();
          if (text[position++] !== ":") invalid();
        }
        const item = value(depth + 1);
        if (object)
          Object.defineProperty(result, key, {
            value: item,
            enumerable: true,
            configurable: true,
            writable: true,
          });
        else result.push(item);
        whitespace();
        const next = text[position++];
        if (next === end) return result;
        if (next !== ",") invalid();
      }
      invalid();
    }
    for (const [token, decoded] of [
      ["true", true],
      ["false", false],
      ["null", null],
    ]) {
      if (text.startsWith(token, position)) {
        position += token.length;
        return decoded;
      }
    }
    const number = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
    number.lastIndex = position;
    const match = number.exec(text);
    if (!match) invalid();
    position = number.lastIndex;
    const decoded = Number(match[0]);
    if (!Number.isFinite(decoded))
      throw new Error("JSONに扱えない大きさの数値が含まれています。");
    return decoded;
  };
  const result = value(0);
  whitespace();
  if (position !== text.length) invalid();
  return result;
}

export async function readJSONFile(file, limit, sizeMessage) {
  if (file.size > limit) throw new Error(sizeMessage);
  return parseStrictJSON(await file.text());
}
