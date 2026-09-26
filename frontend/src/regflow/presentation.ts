export function sourceColumnLabel(column: { index: number; header: string | null; excel_column: string | null }): string {
  const name = column.header || 'Unnamed column'
  return `${name} — Column ${column.excel_column || excelColumn(column.index)}`
}

function excelColumn(index: number): string {
  let result = ''
  let value = index
  while (value > 0) {
    value -= 1
    result = String.fromCharCode(65 + (value % 26)) + result
    value = Math.floor(value / 26)
  }
  return result
}
