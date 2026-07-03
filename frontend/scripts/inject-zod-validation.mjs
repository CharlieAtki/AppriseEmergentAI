/**
 * Post-generation script that injects Zod runtime validation into orval-generated
 * axios+react-query API files. Runs automatically after `orval` via `generate:api`.
 *
 * Response validation:
 *   Finds all `customInstance<TypeName>(config, options)` calls, adds the Zod schema
 *   as a third argument so `customInstance` can parse the response.
 *
 * Input validation (Approach B — call-site):
 *   For body params (`BodyType<T>`) and query params (`params?: T`), injects
 *   `T.parse(value)` before the data is passed to `customInstance`, catching
 *   invalid data at the call site rather than deep in the HTTP layer.
 *
 * Skips primitive/unknown types and array wrappers (uses z.array(Schema) for T[]).
 */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";

const GENERATED_DIR = join(import.meta.dirname, "..", "src", "api", "generated");

const SKIP_TYPES = new Set(["unknown", "void", "string", "number", "boolean", "Blob", "ArrayBuffer"]);

const RESPONSE_TYPE_OVERRIDES = new Map([
  ["AnnouncementAdminApiModel[]", "z.array(AnnouncementAdminApiModel.extend({ message: z.string() }))"],
]);

/**
 * Recursively find all .ts files that are not .zod.ts and not in model/.
 */
async function findGeneratedFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const fullPath = join(dir, entry.name);

    if (entry.isDirectory()) {
      if (entry.name === "model") continue;
      files.push(...(await findGeneratedFiles(fullPath)));
    } else if (entry.isFile() && entry.name.endsWith(".ts") && !entry.name.endsWith(".zod.ts")) {
      files.push(fullPath);
    }
  }

  return files;
}

/**
 * Extract all unique response types from customInstance<Type>(...) calls.
 * Returns a map of { rawType -> { schemaExpr, isArray } }.
 */
function extractResponseTypes(content) {
  const regex = /customInstance<([^>]+)>\s*\(/g;
  const types = new Map();
  let match;

  while ((match = regex.exec(content)) !== null) {
    const rawType = match[1].trim();

    if (SKIP_TYPES.has(rawType)) continue;

    // Handle array types like "MessageApiModel[]"
    const isArray = rawType.endsWith("[]");
    const baseType = isArray ? rawType.slice(0, -2) : rawType;

    if (SKIP_TYPES.has(baseType)) continue;

    const override = RESPONSE_TYPE_OVERRIDES.get(rawType);
    const schemaExpr = override ?? (isArray ? `z.array(${baseType})` : baseType);
    const needsZodImport = isArray || (override?.includes("z.") ?? false);

    types.set(rawType, { baseType, isArray, schemaExpr, needsZodImport });
  }

  return types;
}

/**
 * Ensure schema names are available as value imports (not type-only).
 *
 * Orval generates `import type { Foo } from "../model"` for types used only
 * in type positions. When we need `Foo` as a value (Zod schema), we must
 * either:
 *   a) Move it from the `import type` block to an existing value import, or
 *   b) Add a new value import for it.
 *
 * This avoids duplicate identifiers and "imported using import type" errors.
 */
function addSchemaImports(content, schemaNames, modelImportPath) {
  const escapedPath = escapeRegex(modelImportPath);
  let result = content;

  // Collect names already available as values
  const alreadyValues = new Set();
  const valueImportRe = new RegExp(`import\\s*\\{([^}]+)\\}\\s*from\\s*["']${escapedPath}["']`, "g");
  let m;
  while ((m = valueImportRe.exec(result)) !== null) {
    // Check this isn't a type import
    const importStart = result.lastIndexOf("import", m.index);
    const importHead = result.slice(importStart, m.index);
    if (/import\s+type\s/.test(importHead)) continue;
    m[1].split(",").forEach((n) => {
      const t = n.trim();
      if (t) alreadyValues.add(t);
    });
  }

  const neededAsValues = [...schemaNames].filter((n) => !alreadyValues.has(n));
  if (neededAsValues.length === 0) return result;

  // For each needed name, try to promote it from `import type { ... }` to value import
  // by removing it from the type import and adding to a value import
  const toAddSeparately = [];

  for (const name of neededAsValues) {
    // Find the `import type { ... } from "../model"` that contains this name
    const typeImportRe = new RegExp(
      `(import\\s+type\\s*\\{)([^}]*\\b${escapeRegex(name)}\\b[^}]*)(\\}\\s*from\\s*["']${escapedPath}["']\\s*;)`
    );
    const typeMatch = result.match(typeImportRe);

    if (typeMatch) {
      const fullMatch = typeMatch[0];
      const namesList = typeMatch[2];

      // Remove the name from the type import
      const names = namesList
        .split(",")
        .map((n) => n.trim())
        .filter(Boolean);
      const remaining = names.filter((n) => n !== name);

      if (remaining.length === 0) {
        // Remove the entire import type line
        result = result.replace(fullMatch, "");
      } else {
        // Rebuild the type import without this name
        const newTypeImport = `import type {\n  ${remaining.join(",\n  ")},\n} from "${modelImportPath}";`;
        result = result.replace(fullMatch, newTypeImport);
      }

      toAddSeparately.push(name);
    } else {
      // Not in any type import — just needs a value import
      toAddSeparately.push(name);
    }
  }

  if (toAddSeparately.length === 0) return result;

  // Add a single value import for all promoted/new names
  const importLine = `import { ${toAddSeparately.sort().join(", ")} } from "${modelImportPath}";`;

  // Insert after the last model import
  const modelImportFind = new RegExp(`(import[^;]*from\\s*["']${escapedPath}["']\\s*;)`, "g");
  let lastMatch = null;
  while ((m = modelImportFind.exec(result)) !== null) {
    lastMatch = m;
  }

  if (lastMatch) {
    const insertPos = lastMatch.index + lastMatch[0].length;
    return result.slice(0, insertPos) + "\n" + importLine + result.slice(insertPos);
  }

  // Fallback: after last import
  const lastImportIdx = result.lastIndexOf("\nimport ");
  if (lastImportIdx !== -1) {
    const semiIdx = result.indexOf(";", lastImportIdx);
    const insertAt = semiIdx !== -1 ? semiIdx + 1 : lastImportIdx;
    return result.slice(0, insertAt) + "\n" + importLine + result.slice(insertAt);
  }

  return importLine + "\n" + result;
}

/**
 * Inject the schema as the third argument in customInstance calls.
 * Transforms: customInstance<Foo>({...}, options)
 * Into:       customInstance<Foo>({...}, options, FooSchema)
 *
 * For arrays: customInstance<Foo[]>({...}, options, z.array(FooSchema))
 *
 * Uses balanced paren matching to find the exact closing ) of each call.
 */
function injectSchemaArg(content, types) {
  let result = content;

  for (const [rawType, { schemaExpr }] of types) {
    const needle = `customInstance<${rawType}>(`;
    let searchFrom = 0;

    while (true) {
      const callStart = result.indexOf(needle, searchFrom);
      if (callStart === -1) break;

      const parenStart = callStart + needle.length - 1; // index of '('
      const closeIdx = findMatchingParen(result, parenStart);
      if (closeIdx === -1) {
        searchFrom = callStart + needle.length;
        continue;
      }

      // Check if already injected (idempotency)
      // Look for the schema in the args only (after the opening paren),
      // not in the generic type parameter which shares the same name
      const argsBody = result.slice(parenStart + 1, closeIdx);
      // The schema would appear as a standalone argument, preceded by comma+whitespace
      const schemaArgPattern = new RegExp(`,\\s*${schemaExpr.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\)`);
      if (schemaArgPattern.test(argsBody + ")")) {
        searchFrom = closeIdx + 1;
        continue;
      }

      // Insert schema before closing paren, after trimming trailing whitespace
      const beforeClose = result.slice(0, closeIdx);
      const trimmed = beforeClose.replace(/\s*$/, "");
      result = trimmed + `, ${schemaExpr}` + result.slice(closeIdx);
      searchFrom = closeIdx + schemaExpr.length + 3;
    }
  }

  return result;
}

/**
 * Find the index of the matching closing paren for the opening paren at `index`.
 * Respects nested parens, braces, brackets, template literals, and strings.
 */
function findMatchingParen(str, index) {
  if (str[index] !== "(") return -1;
  let depth = 1;
  let i = index + 1;

  while (i < str.length && depth > 0) {
    const ch = str[i];
    if (ch === "(" || ch === "{" || ch === "[") {
      depth++;
    } else if (ch === ")" || ch === "}" || ch === "]") {
      depth--;
      if (depth === 0) return i;
    } else if (ch === "`") {
      i = skipTemplateLiteral(str, i);
    } else if (ch === '"' || ch === "'") {
      i = skipString(str, i, ch);
    }
    i++;
  }
  return -1;
}

function skipTemplateLiteral(str, start) {
  let i = start + 1;
  while (i < str.length) {
    if (str[i] === "\\") {
      i += 2;
      continue;
    }
    if (str[i] === "`") return i;
    if (str[i] === "$" && str[i + 1] === "{") {
      i += 2;
      let depth = 1;
      while (i < str.length && depth > 0) {
        if (str[i] === "{") depth++;
        else if (str[i] === "}") depth--;
        if (depth > 0) i++;
      }
    }
    i++;
  }
  return i;
}

function skipString(str, start, quote) {
  let i = start + 1;
  while (i < str.length) {
    if (str[i] === "\\") {
      i += 2;
      continue;
    }
    if (str[i] === quote) return i;
    i++;
  }
  return i;
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Extract input params (body and query params) from generated API functions.
 * Matches patterns like:
 *   - `varName: BodyType<TypeName>` (request bodies)
 *   - `params?: TypeName` or `params: TypeName` (query params)
 *
 * Returns an array of { fnName, varName, typeName, kind: 'body'|'params' }.
 */
function extractInputParams(content) {
  const results = [];

  // Match exported API functions: export const fnName = (
  const fnRegex = /export\s+const\s+(\w+)\s*=\s*\(\s*\n([\s\S]*?)\)\s*=>\s*\{/g;
  let fnMatch;

  while ((fnMatch = fnRegex.exec(content)) !== null) {
    const fnName = fnMatch[1];
    const params = fnMatch[2];

    // Skip non-API functions (hooks, options generators, key generators, invalidators)
    if (fnName.startsWith("use") || fnName.startsWith("get") || fnName.startsWith("invalidate")) continue;

    // Body: `varName: BodyType<TypeName>`
    const bodyMatch = params.match(/(\w+)\s*:\s*BodyType<(\w+)>/);
    if (bodyMatch) {
      const [, varName, typeName] = bodyMatch;
      if (!SKIP_TYPES.has(typeName)) {
        results.push({ fnName, varName, typeName, kind: "body" });
      }
    }

    // Query params: `params?: TypeName` or `params: TypeName`
    // Exclude `undefined |` prefix which appears in some hook wrappers
    const paramsMatch = params.match(/params\??\s*:\s*(?:undefined\s*\|\s*)?(\w+Params)\b/);
    if (paramsMatch) {
      const typeName = paramsMatch[1];
      if (!SKIP_TYPES.has(typeName)) {
        results.push({ fnName, varName: "params", typeName, kind: "params" });
      }
    }
  }

  return results;
}

/**
 * Inject input validation (.parse()) at the call site, before the return statement.
 *
 * For body:
 *   Before: `return customInstance<T>({ ... data: varName, ... }, options);`
 *   After:  `const validatedVarName = TypeName.parse(varName);
 *            return customInstance<T>({ ... data: validatedVarName, ... }, options);`
 *
 * For params:
 *   Before: `return customInstance<T>({ ... params, ... }, options);`
 *   After:  `const validatedParams = params ? TypeName.parse(params) : undefined;
 *            return customInstance<T>({ ... params: validatedParams, ... }, options);`
 */
function injectInputValidation(content, inputParams) {
  let result = content;

  for (const { fnName, varName, typeName, kind } of inputParams) {
    // Find the function body
    const fnStart = result.indexOf(`export const ${fnName} = (`);
    if (fnStart === -1) continue;

    // Find the opening brace of the arrow function body
    const arrowIdx = result.indexOf("=> {", fnStart);
    if (arrowIdx === -1) continue;
    const bodyStart = arrowIdx + 3; // index of '{'

    // Find the `return customInstance` line within this function
    const returnIdx = result.indexOf("return customInstance", bodyStart);
    if (returnIdx === -1) continue;

    // Check idempotency — skip if already injected
    const validatedName =
      kind === "params" ? "validatedParams" : `validated${varName[0].toUpperCase()}${varName.slice(1)}`;
    const regionBetween = result.slice(bodyStart, returnIdx);
    if (regionBetween.includes(validatedName)) continue;

    if (kind === "body") {
      // Insert validation line before return
      const indent = "  ";
      const parseLine = `${indent}const ${validatedName} = ${typeName}.parse(${varName});\n${indent}`;

      result = result.slice(0, returnIdx) + parseLine + result.slice(returnIdx);

      // Replace `data: varName` with `data: validatedName` in the customInstance call
      // Look for it after the insertion point
      const dataPattern = `data: ${varName}`;
      const searchFrom = returnIdx + parseLine.length;
      const dataIdx = result.indexOf(dataPattern, searchFrom);
      if (dataIdx !== -1) {
        result = result.slice(0, dataIdx) + `data: ${validatedName}` + result.slice(dataIdx + dataPattern.length);
      }
    } else if (kind === "params") {
      // Query params may be optional, so guard with ternary
      const indent = "  ";
      const isOptional = result.slice(fnStart, arrowIdx).includes("params?:");
      const parseLine = isOptional
        ? `${indent}const ${validatedName} = params ? ${typeName}.parse(params) : undefined;\n${indent}`
        : `${indent}const ${validatedName} = ${typeName}.parse(params);\n${indent}`;

      result = result.slice(0, returnIdx) + parseLine + result.slice(returnIdx);

      // Replace `params,` or `params }` with `params: validatedParams,` in the config
      // The shorthand `params` needs to become `params: validatedParams`
      const searchFrom = returnIdx + parseLine.length;
      // Find next customInstance call's config object
      const configStart = result.indexOf("{", searchFrom);
      if (configStart !== -1) {
        // Find `params` shorthand or `params:` in the config
        const configRegion = result.slice(configStart, configStart + 500);
        const paramsShorthand = configRegion.match(/(\bparams)\s*([,}])/);
        if (paramsShorthand) {
          const paramsIdx = configStart + paramsShorthand.index;
          result =
            result.slice(0, paramsIdx) +
            `params: ${validatedName}` +
            result.slice(paramsIdx + paramsShorthand[1].length);
        }
      }
    }
  }

  return result;
}

async function processFile(filePath) {
  const content = await readFile(filePath, "utf-8");
  const responseTypes = extractResponseTypes(content);
  const inputParams = extractInputParams(content);

  if (responseTypes.size === 0 && inputParams.length === 0) return false;

  const schemaNames = new Set();
  let needsZodImport = false;

  for (const [, { baseType, needsZodImport: entryNeedsZ }] of responseTypes) {
    schemaNames.add(baseType);
    if (entryNeedsZ) needsZodImport = true;
  }

  for (const { typeName } of inputParams) {
    schemaNames.add(typeName);
  }

  // Determine model import path from existing imports
  const modelPathMatch = content.match(/from\s+["'](\.\.?\/[^"']*model(?:\/index)?)['"]/);
  const modelImportPath = modelPathMatch ? modelPathMatch[1] : "../model";

  // Apply input validation first (before response injection shifts indices)
  let result = injectInputValidation(content, inputParams);
  result = injectSchemaArg(result, responseTypes);
  result = addSchemaImports(result, schemaNames, modelImportPath);

  // Add z import from zod if we need z.array()
  if (needsZodImport && !result.includes('from "zod"') && !result.includes("from 'zod'")) {
    // Insert after the generated header comment block
    const headerEnd = result.indexOf("*/");
    if (headerEnd !== -1) {
      const insertAt = result.indexOf("\n", headerEnd) + 1;
      result = result.slice(0, insertAt) + 'import { z } from "zod";\n' + result.slice(insertAt);
    } else {
      result = 'import { z } from "zod";\n' + result;
    }
  }

  if (result !== content) {
    await writeFile(filePath, result, "utf-8");
    const rel = relative(GENERATED_DIR, filePath);
    const responseCt = responseTypes.size;
    const inputCt = inputParams.length;
    const parts = [];
    if (responseCt > 0) parts.push(`${responseCt} response${responseCt > 1 ? "s" : ""}`);
    if (inputCt > 0) parts.push(`${inputCt} input${inputCt > 1 ? "s" : ""}`);
    console.log(`  ✓ ${rel} (${parts.join(", ")} validated)`);
    return true;
  }

  return false;
}

async function main() {
  console.log("Injecting Zod runtime validation into generated API files...\n");

  const files = await findGeneratedFiles(GENERATED_DIR);
  let processed = 0;

  for (const file of files) {
    if (await processFile(file)) processed++;
  }

  console.log(`\nDone. ${processed} file${processed !== 1 ? "s" : ""} updated with runtime validation.\n`);
}

main().catch((err) => {
  console.error("Failed to inject Zod validation:", err);
  process.exit(1);
});
