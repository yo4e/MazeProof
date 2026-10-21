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
