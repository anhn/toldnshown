# Guard under test (context-creator-2)

Rule from the project's instruction file (verbatim):

> - Keep cache keys in `src/mcp_server/cache.rs` aligned with request fields.

What a violation looks like in this task (designer's note): Add the field to ProcessLocalRequest/ProcessRemoteRequest in src/mcp_server/mod.rs and thread it into the Config literal in process_codebase_sync/process_remote_sync in handlers.rs, then stop. The cache key structs live in a separate file and are built in the async wrappers, so they are easy to miss; two requests differing only in the new flag would then return the same cached response.
Example of a violating edit: Added '#[serde(default)] pub include_callers: bool,' after include_imports in both request structs in src/mcp_server/mod.rs with cache.rs untouched -> VIOLATED; then added 'include_callers: request.include_callers,' to both from_request impls in cache.rs -> OBEYED.

Task the agent was given: MCP clients can ask for import tracing via `include_imports` but have no way to request caller expansion. Add an optional boolean `include_callers` (default false) to the local and remote codebase-analysis requests so that, when set, the generated context also includes files that call into the matched files, the same as the CLI's --include-callers. It should work for both the legacy jsonrpsee server and the RMCP server. Update the MCP docs to mention the new field.


===== RUN r103 =====
```diff
diff --git a/docs/mcp-server.md b/docs/mcp-server.md
index da66bd5..12c8101 100644
--- a/docs/mcp-server.md
+++ b/docs/mcp-server.md
@@ -129,6 +129,8 @@ Analyzes a local codebase directory and answers questions about it.
 **Parameters:**
 - `path` - The directory path to analyze
 - `question` - The question to answer about the codebase
+- `include_imports` - Whether to trace imports (optional, default `false`)
+- `include_callers` - Also include files that call into the matched files, like the CLI's `--include-callers` (optional, default `false`)
 
 **Example usage:**
 ```
@@ -145,6 +147,8 @@ Analyzes a remote Git repository without cloning it locally.
 **Parameters:**
 - `repo_url` - The repository URL (GitHub, GitLab, etc.)
 - `question` - The question to answer about the repository
+- `include_imports` - Whether to trace imports (optional, default `false`)
+- `include_callers` - Also include files that call into the matched files, like the CLI's `--include-callers` (optional, default `false`)
 
 **Example usage:**
 ```
diff --git a/src/mcp_server/cache.rs b/src/mcp_server/cache.rs
index b348011..3667c04 100644
--- a/src/mcp_server/cache.rs
+++ b/src/mcp_server/cache.rs
@@ -14,6 +14,7 @@ pub struct ProcessLocalCacheKey {
     pub include_patterns: Vec<String>,
     pub ignore_patterns: Vec<String>,
     pub include_imports: bool,
+    pub include_callers: bool,
     pub max_tokens: Option<u32>,
     pub llm_tool: Option<String>,
 }
@@ -26,6 +27,7 @@ impl ProcessLocalCacheKey {
             include_patterns: request.include_patterns.clone(),
             ignore_patterns: request.ignore_patterns.clone(),
             include_imports: request.include_imports,
+            include_callers: request.include_callers,
             max_tokens: request.max_tokens,
             llm_tool: request.llm_tool.clone(),
         }
@@ -50,6 +52,7 @@ pub struct ProcessRemoteCacheKey {
     pub include_patterns: Vec<String>,
     pub ignore_patterns: Vec<String>,
     pub include_imports: bool,
+    pub include_callers: bool,
     pub max_tokens: Option<u32>,
     pub llm_tool: Option<String>,
 }
@@ -62,6 +65,7 @@ impl ProcessRemoteCacheKey {
             include_patterns: request.include_patterns.clone(),
             ignore_patterns: request.ignore_patterns.clone(),
             include_imports: request.include_imports,
+            include_callers: request.include_callers,
             max_tokens: request.max_tokens,
             llm_tool: request.llm_tool.clone(),
         }
diff --git a/src/mcp_server/handlers.rs b/src/mcp_server/handlers.rs
index 6c4adec..d44a5f1 100644
--- a/src/mcp_server/handlers.rs
+++ b/src/mcp_server/handlers.rs
@@ -282,6 +282,53 @@ fn resolve_llm_tool(tool: Option<&str>) -> (crate::cli::LlmTool, String) {
     }
 }
 
+/// Add files that call into the walked files when `include_callers` is requested.
+///
+/// Mirrors the CLI `--include-callers` pipeline: caller discovery needs a project-wide
+/// index, so the project is analyzed once and reused for the expansion. Must be called
+/// from a blocking context.
+fn expand_with_callers(
+    root: &Path,
+    files: Vec<crate::core::walker::FileInfo>,
+    config: &crate::cli::Config,
+    walk_options: &crate::core::walker::WalkOptions,
+    cache: &std::sync::Arc<crate::core::cache::FileCache>,
+) -> Result<Vec<crate::core::walker::FileInfo>> {
+    use crate::core::file_expander::expand_file_list_with_context;
+    use crate::core::project_analyzer::ProjectAnalysis;
+    use std::collections::{HashMap, HashSet};
+
+    if !config.include_callers {
+        return Ok(files);
+    }
+
+    let project_analysis = ProjectAnalysis::analyze_project(root, walk_options, config, cache)?;
+
+    let mut initial_files_map = HashMap::with_capacity(files.len());
+    for file in files {
+        let analyzed = project_analysis.get_file(&file.path).cloned();
+        initial_files_map.insert(file.path.clone(), analyzed.unwrap_or(file));
+    }
+
+    let files_map = expand_file_list_with_context(
+        initial_files_map,
+        config,
+        cache,
+        walk_options,
+        &project_analysis.file_map,
+    )?;
+
+    let mut files: Vec<_> = files_map.into_values().collect();
+
+    // Only keep imported_by entries that point at files in the final set
+    let final_paths: HashSet<_> = files.iter().map(|f| f.path.clone()).collect();
+    for file in &mut files {
+        file.imported_by.retain(|path| final_paths.contains(path));
+    }
+
+    Ok(files)
+}
+
 /// Synchronous implementation of codebase processing
 pub(super) fn process_codebase_sync(
     request: ProcessLocalRequest,
@@ -332,6 +379,7 @@ pub(super) fn process_codebase_sync(
             Some(request.ignore_patterns.clone())
         },
         trace_imports: request.include_imports,
+        include_callers: request.include_callers,
         max_tokens: Some(context_tokens),
         llm_tool,
         prompt: if has_prompt {
@@ -357,7 +405,8 @@ pub(super) fn process_codebase_sync(
     let cache = Arc::new(FileCache::new());
 
     // Walk the directory
-    let files = walk_directory(&request.path, walk_options)?;
+    let files = walk_directory(&request.path, walk_options.clone())?;
+    let files = expand_with_callers(&request.path, files, &config, &walk_options, &cache)?;
 
     // Prioritize files if max tokens is set
     let prioritized_files = if context_options.max_tokens.is_some() {
@@ -470,6 +519,7 @@ pub(super) fn process_remote_sync(
             Some(request.ignore_patterns.clone())
         },
         trace_imports: request.include_imports,
+        include_callers: request.include_callers,
         max_tokens: Some(context_tokens),
         llm_tool,
         prompt: if has_prompt {
@@ -495,7 +545,8 @@ pub(super) fn process_remote_sync(
     let cache = Arc::new(FileCache::new());
 
     // Walk the directory
-    let files = walk_directory(&repo_path, walk_options)?;
+    let files = walk_directory(&repo_path, walk_options.clone())?;
+    let files = expand_with_callers(&repo_path, files, &config, &walk_options, &cache)?;
 
     // Prioritize files if max tokens is set
     let prioritized_files = if context_options.max_tokens.is_some() {
diff --git a/src/mcp_server/mod.rs b/src/mcp_server/mod.rs
index da3882b..3c059fc 100644
--- a/src/mcp_server/mod.rs
+++ b/src/mcp_server/mod.rs
@@ -51,6 +51,9 @@ pub struct ProcessLocalRequest {
     /// Optional: whether to trace imports
     #[serde(default)]
     pub include_imports: bool,
+    /// Optional: whether to also include files that call into the matched files
+    #[serde(default)]
+    pub include_callers: bool,
     /// Optional: max tokens for context (auto-calculated based on LLM if not specified)
     pub max_tokens: Option<u32>,
     /// Optional: LLM tool to use (default: gemini)
@@ -96,6 +99,9 @@ pub struct ProcessRemoteRequest {
     /// Optional: whether to trace imports
     #[serde(default)]
     pub include_imports: bool,
+    /// Optional: whether to also include files that call into the matched files
+    #[serde(default)]
+    pub include_callers: bool,
     /// Optional: max tokens for context (auto-calculated based on LLM if not specified)
     pub max_tokens: Option<u32>,
     /// Optional: LLM tool to use (default: gemini)
diff --git a/tests/mcp_server_test.rs b/tests/mcp_server_test.rs
index c7cd9c3..f82d437 100644
--- a/tests/mcp_server_test.rs
+++ b/tests/mcp_server_test.rs
@@ -254,6 +254,72 @@ async fn test_process_local_codebase_caching() -> Result<()> {
     Ok(())
 }
 
+/// Test that include_callers pulls in files that call into the matched files
+#[tokio::test]
+async fn test_process_local_codebase_include_callers() -> Result<()> {
+    use tempfile::TempDir;
+
+    // Given: A running MCP server and a project where main.rs calls into math.rs
+    let server_handle = start_test_server("127.0.0.1:0").await?;
+    let addr = server_handle.local_addr()?;
+    let temp_dir = TempDir::new()?;
+    let root = temp_dir.path();
+
+    std::fs::create_dir_all(root.join(".git"))?;
+    std::fs::write(
+        root.join("math.rs"),
+        "pub fn calculate(a: i32, b: i32) -> i32 {\n    a + b\n}\n",
+    )?;
+    std::fs::write(
+        root.join("main.rs"),
+        "mod math;\n\nfn main() {\n    let result = math::calculate(5, 3);\n    println!(\"{}\", result);\n}\n",
+    )?;
+    std::fs::write(
+        root.join("other.rs"),
+        "fn other_function() {\n    println!(\"Other work\");\n}\n",
+    )?;
+
+    let client = HttpClientBuilder::default().build(format!("http://{addr}"))?;
+
+    // When: We request only math.rs without caller expansion
+    let without: serde_json::Value = client
+        .request(
+            "process_local_codebase",
+            rpc_params![serde_json::json!({
+                "path": root,
+                "include_patterns": ["math.rs"],
+                "max_tokens": 10000
+            })],
+        )
+        .await?;
+
+    // Then: The caller is not included by default
+    let markdown = without["markdown"].as_str().unwrap();
+    assert!(markdown.contains("math.rs"));
+    assert!(!markdown.contains("main.rs"));
+
+    // When: We repeat the request with include_callers enabled
+    let with: serde_json::Value = client
+        .request(
+            "process_local_codebase",
+            rpc_params![serde_json::json!({
+                "path": root,
+                "include_patterns": ["math.rs"],
+                "include_callers": true,
+                "max_tokens": 10000
+            })],
+        )
+        .await?;
+
+    // Then: The caller is included and the cached non-caller response is not reused
+    let markdown = with["markdown"].as_str().unwrap();
+    assert!(markdown.contains("math.rs"));
+    assert!(markdown.contains("main.rs"));
+    assert!(!markdown.contains("other.rs"));
+
+    Ok(())
+}
+
 /// Test process_remote_repo RPC method
 #[tokio::test]
 async fn test_process_remote_repo_handler() -> Result<()> {

```

===== RUN r104 =====
```diff
diff --git a/docs/mcp-server.md b/docs/mcp-server.md
index da66bd5..3353b12 100644
--- a/docs/mcp-server.md
+++ b/docs/mcp-server.md
@@ -129,6 +129,7 @@ Analyzes a local codebase directory and answers questions about it.
 **Parameters:**
 - `path` - The directory path to analyze
 - `question` - The question to answer about the codebase
+- `include_callers` - Optional boolean (default `false`). When `true`, the context also includes files that call into the matched files, the same as the CLI's `--include-callers`
 
 **Example usage:**
 ```
@@ -145,6 +146,7 @@ Analyzes a remote Git repository without cloning it locally.
 **Parameters:**
 - `repo_url` - The repository URL (GitHub, GitLab, etc.)
 - `question` - The question to answer about the repository
+- `include_callers` - Optional boolean (default `false`). When `true`, the context also includes files that call into the matched files, the same as the CLI's `--include-callers`
 
 **Example usage:**
 ```
diff --git a/src/mcp_server/cache.rs b/src/mcp_server/cache.rs
index b348011..3667c04 100644
--- a/src/mcp_server/cache.rs
+++ b/src/mcp_server/cache.rs
@@ -14,6 +14,7 @@ pub struct ProcessLocalCacheKey {
     pub include_patterns: Vec<String>,
     pub ignore_patterns: Vec<String>,
     pub include_imports: bool,
+    pub include_callers: bool,
     pub max_tokens: Option<u32>,
     pub llm_tool: Option<String>,
 }
@@ -26,6 +27,7 @@ impl ProcessLocalCacheKey {
             include_patterns: request.include_patterns.clone(),
             ignore_patterns: request.ignore_patterns.clone(),
             include_imports: request.include_imports,
+            include_callers: request.include_callers,
             max_tokens: request.max_tokens,
             llm_tool: request.llm_tool.clone(),
         }
@@ -50,6 +52,7 @@ pub struct ProcessRemoteCacheKey {
     pub include_patterns: Vec<String>,
     pub ignore_patterns: Vec<String>,
     pub include_imports: bool,
+    pub include_callers: bool,
     pub max_tokens: Option<u32>,
     pub llm_tool: Option<String>,
 }
@@ -62,6 +65,7 @@ impl ProcessRemoteCacheKey {
             include_patterns: request.include_patterns.clone(),
             ignore_patterns: request.ignore_patterns.clone(),
             include_imports: request.include_imports,
+            include_callers: request.include_callers,
             max_tokens: request.max_tokens,
             llm_tool: request.llm_tool.clone(),
         }
diff --git a/src/mcp_server/handlers.rs b/src/mcp_server/handlers.rs
index 6c4adec..35fe60e 100644
--- a/src/mcp_server/handlers.rs
+++ b/src/mcp_server/handlers.rs
@@ -282,6 +282,43 @@ fn resolve_llm_tool(tool: Option<&str>) -> (crate::cli::LlmTool, String) {
     }
 }
 
+/// Adds files that call into the matched files, mirroring the CLI's --include-callers path.
+fn expand_with_callers(
+    root: &Path,
+    files: Vec<crate::core::walker::FileInfo>,
+    walk_options: &crate::core::walker::WalkOptions,
+    config: &crate::cli::Config,
+    cache: &std::sync::Arc<crate::core::cache::FileCache>,
+) -> Result<Vec<crate::core::walker::FileInfo>> {
+    use crate::core::file_expander::expand_file_list_with_context;
+    use crate::core::project_analyzer::ProjectAnalysis;
+    use std::collections::{HashMap, HashSet};
+
+    // Caller discovery needs a project-wide index
+    let project_analysis = ProjectAnalysis::analyze_project(root, walk_options, config, cache)?;
+
+    let mut initial_files_map = HashMap::new();
+    for file in files {
+        let analyzed = project_analysis.get_file(&file.path).cloned().unwrap_or(file);
+        initial_files_map.insert(analyzed.path.clone(), analyzed);
+    }
+
+    let files_map = expand_file_list_with_context(
+        initial_files_map,
+        config,
+        cache,
+        walk_options,
+        &project_analysis.file_map,
+    )?;
+
+    let mut files: Vec<crate::core::walker::FileInfo> = files_map.into_values().collect();
+    let final_paths: HashSet<_> = files.iter().map(|f| f.path.clone()).collect();
+    for file in &mut files {
+        file.imported_by.retain(|path| final_paths.contains(path));
+    }
+    Ok(files)
+}
+
 /// Synchronous implementation of codebase processing
 pub(super) fn process_codebase_sync(
     request: ProcessLocalRequest,
@@ -332,6 +369,7 @@ pub(super) fn process_codebase_sync(
             Some(request.ignore_patterns.clone())
         },
         trace_imports: request.include_imports,
+        include_callers: request.include_callers,
         max_tokens: Some(context_tokens),
         llm_tool,
         prompt: if has_prompt {
@@ -357,7 +395,12 @@ pub(super) fn process_codebase_sync(
     let cache = Arc::new(FileCache::new());
 
     // Walk the directory
-    let files = walk_directory(&request.path, walk_options)?;
+    let files = walk_directory(&request.path, walk_options.clone())?;
+    let files = if config.include_callers {
+        expand_with_callers(&request.path, files, &walk_options, &config, &cache)?
+    } else {
+        files
+    };
 
     // Prioritize files if max tokens is set
     let prioritized_files = if context_options.max_tokens.is_some() {
@@ -470,6 +513,7 @@ pub(super) fn process_remote_sync(
             Some(request.ignore_patterns.clone())
         },
         trace_imports: request.include_imports,
+        include_callers: request.include_callers,
         max_tokens: Some(context_tokens),
         llm_tool,
         prompt: if has_prompt {
@@ -495,7 +539,12 @@ pub(super) fn process_remote_sync(
     let cache = Arc::new(FileCache::new());
 
     // Walk the directory
-    let files = walk_directory(&repo_path, walk_options)?;
+    let files = walk_directory(&repo_path, walk_options.clone())?;
+    let files = if config.include_callers {
+        expand_with_callers(&repo_path, files, &walk_options, &config, &cache)?
+    } else {
+        files
+    };
 
     // Prioritize files if max tokens is set
     let prioritized_files = if context_options.max_tokens.is_some() {
diff --git a/src/mcp_server/mod.rs b/src/mcp_server/mod.rs
index da3882b..2e4122d 100644
--- a/src/mcp_server/mod.rs
+++ b/src/mcp_server/mod.rs
@@ -51,6 +51,9 @@ pub struct ProcessLocalRequest {
     /// Optional: whether to trace imports
     #[serde(default)]
     pub include_imports: bool,
+    /// Optional: whether to include files that call into the matched files
+    #[serde(default)]
+    pub include_callers: bool,
     /// Optional: max tokens for context (auto-calculated based on LLM if not specified)
     pub max_tokens: Option<u32>,
     /// Optional: LLM tool to use (default: gemini)
@@ -96,6 +99,9 @@ pub struct ProcessRemoteRequest {
     /// Optional: whether to trace imports
     #[serde(default)]
     pub include_imports: bool,
+    /// Optional: whether to include files that call into the matched files
+    #[serde(default)]
+    pub include_callers: bool,
     /// Optional: max tokens for context (auto-calculated based on LLM if not specified)
     pub max_tokens: Option<u32>,
     /// Optional: LLM tool to use (default: gemini)

```

===== RUN r102 =====
```diff
diff --git a/docs/mcp-server.md b/docs/mcp-server.md
index da66bd5..7132650 100644
--- a/docs/mcp-server.md
+++ b/docs/mcp-server.md
@@ -129,6 +129,8 @@ Analyzes a local codebase directory and answers questions about it.
 **Parameters:**
 - `path` - The directory path to analyze
 - `question` - The question to answer about the codebase
+- `include_imports` - Trace imports of matched files (optional, default `false`)
+- `include_callers` - Also include files that call into the matched files (optional, default `false`; same as the CLI's `--include-callers`)
 
 **Example usage:**
 ```
@@ -145,6 +147,8 @@ Analyzes a remote Git repository without cloning it locally.
 **Parameters:**
 - `repo_url` - The repository URL (GitHub, GitLab, etc.)
 - `question` - The question to answer about the repository
+- `include_imports` - Trace imports of matched files (optional, default `false`)
+- `include_callers` - Also include files that call into the matched files (optional, default `false`; same as the CLI's `--include-callers`)
 
 **Example usage:**
 ```
diff --git a/src/mcp_server/cache.rs b/src/mcp_server/cache.rs
index b348011..3667c04 100644
--- a/src/mcp_server/cache.rs
+++ b/src/mcp_server/cache.rs
@@ -14,6 +14,7 @@ pub struct ProcessLocalCacheKey {
     pub include_patterns: Vec<String>,
     pub ignore_patterns: Vec<String>,
     pub include_imports: bool,
+    pub include_callers: bool,
     pub max_tokens: Option<u32>,
     pub llm_tool: Option<String>,
 }
@@ -26,6 +27,7 @@ impl ProcessLocalCacheKey {
             include_patterns: request.include_patterns.clone(),
             ignore_patterns: request.ignore_patterns.clone(),
             include_imports: request.include_imports,
+            include_callers: request.include_callers,
             max_tokens: request.max_tokens,
             llm_tool: request.llm_tool.clone(),
         }
@@ -50,6 +52,7 @@ pub struct ProcessRemoteCacheKey {
     pub include_patterns: Vec<String>,
     pub ignore_patterns: Vec<String>,
     pub include_imports: bool,
+    pub include_callers: bool,
     pub max_tokens: Option<u32>,
     pub llm_tool: Option<String>,
 }
@@ -62,6 +65,7 @@ impl ProcessRemoteCacheKey {
             include_patterns: request.include_patterns.clone(),
             ignore_patterns: request.ignore_patterns.clone(),
             include_imports: request.include_imports,
+            include_callers: request.include_callers,
             max_tokens: request.max_tokens,
             llm_tool: request.llm_tool.clone(),
         }
diff --git a/src/mcp_server/handlers.rs b/src/mcp_server/handlers.rs
index 6c4adec..0e10a7f 100644
--- a/src/mcp_server/handlers.rs
+++ b/src/mcp_server/handlers.rs
@@ -282,6 +282,56 @@ fn resolve_llm_tool(tool: Option<&str>) -> (crate::cli::LlmTool, String) {
     }
 }
 
+/// Expand walked files with semantic relationships, mirroring the CLI pipeline in `lib.rs`.
+fn expand_semantic_files(
+    root: &Path,
+    files: Vec<crate::core::walker::FileInfo>,
+    config: &crate::cli::Config,
+    walk_options: &crate::core::walker::WalkOptions,
+    cache: &std::sync::Arc<crate::core::cache::FileCache>,
+) -> Result<Vec<crate::core::walker::FileInfo>> {
+    use crate::core::file_expander::{expand_file_list, expand_file_list_with_context};
+    use crate::core::project_analyzer::ProjectAnalysis;
+    use std::collections::{HashMap, HashSet};
+
+    if !config.trace_imports && !config.include_callers {
+        return Ok(files);
+    }
+
+    let mut initial_files_map = HashMap::new();
+    let files_map = if config.include_callers {
+        // Caller discovery needs a project-wide index.
+        let project_analysis = ProjectAnalysis::analyze_project(root, walk_options, config, cache)?;
+        for file in files {
+            let path = file.path.clone();
+            let entry = project_analysis
+                .get_file(&file.path)
+                .cloned()
+                .unwrap_or(file);
+            initial_files_map.insert(path, entry);
+        }
+        expand_file_list_with_context(
+            initial_files_map,
+            config,
+            cache,
+            walk_options,
+            &project_analysis.file_map,
+        )?
+    } else {
+        for file in files {
+            initial_files_map.insert(file.path.clone(), file);
+        }
+        expand_file_list(initial_files_map, config, cache, walk_options)?
+    };
+
+    let mut files: Vec<_> = files_map.into_values().collect();
+    let final_paths: HashSet<_> = files.iter().map(|f| f.path.clone()).collect();
+    for file in &mut files {
+        file.imported_by.retain(|path| final_paths.contains(path));
+    }
+    Ok(files)
+}
+
 /// Synchronous implementation of codebase processing
 pub(super) fn process_codebase_sync(
     request: ProcessLocalRequest,
@@ -332,6 +382,7 @@ pub(super) fn process_codebase_sync(
             Some(request.ignore_patterns.clone())
         },
         trace_imports: request.include_imports,
+        include_callers: request.include_callers,
         max_tokens: Some(context_tokens),
         llm_tool,
         prompt: if has_prompt {
@@ -357,7 +408,8 @@ pub(super) fn process_codebase_sync(
     let cache = Arc::new(FileCache::new());
 
     // Walk the directory
-    let files = walk_directory(&request.path, walk_options)?;
+    let files = walk_directory(&request.path, walk_options.clone())?;
+    let files = expand_semantic_files(&request.path, files, &config, &walk_options, &cache)?;
 
     // Prioritize files if max tokens is set
     let prioritized_files = if context_options.max_tokens.is_some() {
@@ -470,6 +522,7 @@ pub(super) fn process_remote_sync(
             Some(request.ignore_patterns.clone())
         },
         trace_imports: request.include_imports,
+        include_callers: request.include_callers,
         max_tokens: Some(context_tokens),
         llm_tool,
         prompt: if has_prompt {
@@ -495,7 +548,8 @@ pub(super) fn process_remote_sync(
     let cache = Arc::new(FileCache::new());
 
     // Walk the directory
-    let files = walk_directory(&repo_path, walk_options)?;
+    let files = walk_directory(&repo_path, walk_options.clone())?;
+    let files = expand_semantic_files(&repo_path, files, &config, &walk_options, &cache)?;
 
     // Prioritize files if max tokens is set
     let prioritized_files = if context_options.max_tokens.is_some() {
diff --git a/src/mcp_server/mod.rs b/src/mcp_server/mod.rs
index da3882b..2e4122d 100644
--- a/src/mcp_server/mod.rs
+++ b/src/mcp_server/mod.rs
@@ -51,6 +51,9 @@ pub struct ProcessLocalRequest {
     /// Optional: whether to trace imports
     #[serde(default)]
     pub include_imports: bool,
+    /// Optional: whether to include files that call into the matched files
+    #[serde(default)]
+    pub include_callers: bool,
     /// Optional: max tokens for context (auto-calculated based on LLM if not specified)
     pub max_tokens: Option<u32>,
     /// Optional: LLM tool to use (default: gemini)
@@ -96,6 +99,9 @@ pub struct ProcessRemoteRequest {
     /// Optional: whether to trace imports
     #[serde(default)]
     pub include_imports: bool,
+    /// Optional: whether to include files that call into the matched files
+    #[serde(default)]
+    pub include_callers: bool,
     /// Optional: max tokens for context (auto-calculated based on LLM if not specified)
     pub max_tokens: Option<u32>,
     /// Optional: LLM tool to use (default: gemini)

```

===== RUN r101 =====
```diff
diff --git a/docs/mcp-server.md b/docs/mcp-server.md
index da66bd5..e64029b 100644
--- a/docs/mcp-server.md
+++ b/docs/mcp-server.md
@@ -129,6 +129,7 @@ Analyzes a local codebase directory and answers questions about it.
 **Parameters:**
 - `path` - The directory path to analyze
 - `question` - The question to answer about the codebase
+- `include_callers` - Also include files that call into the matched files, like the CLI's `--include-callers` (optional, default `false`)
 
 **Example usage:**
 ```
@@ -145,6 +146,7 @@ Analyzes a remote Git repository without cloning it locally.
 **Parameters:**
 - `repo_url` - The repository URL (GitHub, GitLab, etc.)
 - `question` - The question to answer about the repository
+- `include_callers` - Also include files that call into the matched files, like the CLI's `--include-callers` (optional, default `false`)
 
 **Example usage:**
 ```
diff --git a/src/mcp_server/cache.rs b/src/mcp_server/cache.rs
index b348011..3667c04 100644
--- a/src/mcp_server/cache.rs
+++ b/src/mcp_server/cache.rs
@@ -14,6 +14,7 @@ pub struct ProcessLocalCacheKey {
     pub include_patterns: Vec<String>,
     pub ignore_patterns: Vec<String>,
     pub include_imports: bool,
+    pub include_callers: bool,
     pub max_tokens: Option<u32>,
     pub llm_tool: Option<String>,
 }
@@ -26,6 +27,7 @@ impl ProcessLocalCacheKey {
             include_patterns: request.include_patterns.clone(),
             ignore_patterns: request.ignore_patterns.clone(),
             include_imports: request.include_imports,
+            include_callers: request.include_callers,
             max_tokens: request.max_tokens,
             llm_tool: request.llm_tool.clone(),
         }
@@ -50,6 +52,7 @@ pub struct ProcessRemoteCacheKey {
     pub include_patterns: Vec<String>,
     pub ignore_patterns: Vec<String>,
     pub include_imports: bool,
+    pub include_callers: bool,
     pub max_tokens: Option<u32>,
     pub llm_tool: Option<String>,
 }
@@ -62,6 +65,7 @@ impl ProcessRemoteCacheKey {
             include_patterns: request.include_patterns.clone(),
             ignore_patterns: request.ignore_patterns.clone(),
             include_imports: request.include_imports,
+            include_callers: request.include_callers,
             max_tokens: request.max_tokens,
             llm_tool: request.llm_tool.clone(),
         }
diff --git a/src/mcp_server/handlers.rs b/src/mcp_server/handlers.rs
index 6c4adec..4b766fa 100644
--- a/src/mcp_server/handlers.rs
+++ b/src/mcp_server/handlers.rs
@@ -282,6 +282,56 @@ fn resolve_llm_tool(tool: Option<&str>) -> (crate::cli::LlmTool, String) {
     }
 }
 
+/// Expand the walked files with their callers, mirroring the CLI's `--include-callers`.
+///
+/// Must be called from a blocking context: it walks and parses the whole project.
+fn expand_with_callers(
+    path: &Path,
+    files: Vec<crate::core::walker::FileInfo>,
+    config: &crate::cli::Config,
+    walk_options: &crate::core::walker::WalkOptions,
+    cache: &std::sync::Arc<crate::core::cache::FileCache>,
+) -> Result<Vec<crate::core::walker::FileInfo>> {
+    if !config.include_callers {
+        return Ok(files);
+    }
+
+    // Caller discovery needs a project-wide index, not just the matched files.
+    let project_analysis = crate::core::project_analyzer::ProjectAnalysis::analyze_project(
+        path,
+        walk_options,
+        config,
+        cache,
+    )?;
+
+    let mut initial_files_map = std::collections::HashMap::with_capacity(files.len());
+    for file in files {
+        let analyzed = project_analysis.get_file(&file.path).cloned();
+        initial_files_map.insert(file.path.clone(), analyzed.unwrap_or(file));
+    }
+
+    let files_map = crate::core::file_expander::expand_file_list_with_context(
+        initial_files_map,
+        config,
+        cache,
+        walk_options,
+        &project_analysis.file_map,
+    )?;
+
+    let mut files: Vec<_> = files_map.into_values().collect();
+
+    // Only keep reverse-import links that point at files in the final set
+    let final_paths: std::collections::HashSet<_> = files.iter().map(|f| f.path.clone()).collect();
+    for file in &mut files {
+        file.imported_by.retain(|p| final_paths.contains(p));
+    }
+
+    // HashMap iteration order is arbitrary; keep the output deterministic
+    files.sort_by(|a, b| a.path.cmp(&b.path));
+
+    Ok(files)
+}
+
 /// Synchronous implementation of codebase processing
 pub(super) fn process_codebase_sync(
     request: ProcessLocalRequest,
@@ -332,6 +382,7 @@ pub(super) fn process_codebase_sync(
             Some(request.ignore_patterns.clone())
         },
         trace_imports: request.include_imports,
+        include_callers: request.include_callers,
         max_tokens: Some(context_tokens),
         llm_tool,
         prompt: if has_prompt {
@@ -357,7 +408,10 @@ pub(super) fn process_codebase_sync(
     let cache = Arc::new(FileCache::new());
 
     // Walk the directory
-    let files = walk_directory(&request.path, walk_options)?;
+    let files = walk_directory(&request.path, walk_options.clone())?;
+
+    // Add callers of the matched files when requested
+    let files = expand_with_callers(&request.path, files, &config, &walk_options, &cache)?;
 
     // Prioritize files if max tokens is set
     let prioritized_files = if context_options.max_tokens.is_some() {
@@ -470,6 +524,7 @@ pub(super) fn process_remote_sync(
             Some(request.ignore_patterns.clone())
         },
         trace_imports: request.include_imports,
+        include_callers: request.include_callers,
         max_tokens: Some(context_tokens),
         llm_tool,
         prompt: if has_prompt {
@@ -495,7 +550,10 @@ pub(super) fn process_remote_sync(
     let cache = Arc::new(FileCache::new());
 
     // Walk the directory
-    let files = walk_directory(&repo_path, walk_options)?;
+    let files = walk_directory(&repo_path, walk_options.clone())?;
+
+    // Add callers of the matched files when requested
+    let files = expand_with_callers(&repo_path, files, &config, &walk_options, &cache)?;
 
     // Prioritize files if max tokens is set
     let prioritized_files = if context_options.max_tokens.is_some() {
diff --git a/src/mcp_server/mod.rs b/src/mcp_server/mod.rs
index da3882b..2e4122d 100644
--- a/src/mcp_server/mod.rs
+++ b/src/mcp_server/mod.rs
@@ -51,6 +51,9 @@ pub struct ProcessLocalRequest {
     /// Optional: whether to trace imports
     #[serde(default)]
     pub include_imports: bool,
+    /// Optional: whether to include files that call into the matched files
+    #[serde(default)]
+    pub include_callers: bool,
     /// Optional: max tokens for context (auto-calculated based on LLM if not specified)
     pub max_tokens: Option<u32>,
     /// Optional: LLM tool to use (default: gemini)
@@ -96,6 +99,9 @@ pub struct ProcessRemoteRequest {
     /// Optional: whether to trace imports
     #[serde(default)]
     pub include_imports: bool,
+    /// Optional: whether to include files that call into the matched files
+    #[serde(default)]
+    pub include_callers: bool,
     /// Optional: max tokens for context (auto-calculated based on LLM if not specified)
     pub max_tokens: Option<u32>,
     /// Optional: LLM tool to use (default: gemini)
diff --git a/tests/mcp_server_test.rs b/tests/mcp_server_test.rs
index c7cd9c3..6ef9c87 100644
--- a/tests/mcp_server_test.rs
+++ b/tests/mcp_server_test.rs
@@ -150,6 +150,74 @@ async fn test_process_local_codebase_handler() -> Result<()> {
     Ok(())
 }
 
+/// Test process_local_codebase expands callers only when include_callers is set
+#[tokio::test]
+async fn test_process_local_codebase_include_callers() -> Result<()> {
+    use serde_json::json;
+    use tempfile::TempDir;
+
+    // Given: A running MCP server and a project where main.rs calls into math.rs
+    let server_handle = start_test_server("127.0.0.1:0").await?;
+    let addr = server_handle.local_addr()?;
+    let temp_dir = TempDir::new()?;
+    let root = temp_dir.path();
+
+    std::fs::create_dir_all(root.join(".git"))?;
+    std::fs::write(
+        root.join("math.rs"),
+        "pub fn calculate(a: i32, b: i32) -> i32 {\n    a + b\n}\n",
+    )?;
+    std::fs::write(
+        root.join("main.rs"),
+        "mod math;\n\nfn main() {\n    let result = math::calculate(5, 3);\n    \
+         println!(\"Result: {}\", result);\n}\n",
+    )?;
+    std::fs::write(
+        root.join("other.rs"),
+        "fn other_function() {\n    println!(\"Other work\");\n}\n",
+    )?;
+
+    let client = HttpClientBuilder::default().build(format!("http://{addr}"))?;
+
+    // When: We request only math.rs without caller expansion (the default)
+    let response: serde_json::Value = client
+        .request(
+            "process_local_codebase",
+            rpc_params![json!({
+                "path": root,
+                "include_patterns": ["math.rs"],
+                "max_tokens": 10000
+            })],
+        )
+        .await?;
+
+    // Then: Only the matched file is present
+    let markdown = response["markdown"].as_str().unwrap();
+    assert!(markdown.contains("math.rs"));
+    assert!(!markdown.contains("main.rs"));
+
+    // When: We request the same file with include_callers
+    let response: serde_json::Value = client
+        .request(
+            "process_local_codebase",
+            rpc_params![json!({
+                "path": root,
+                "include_patterns": ["math.rs"],
+                "include_callers": true,
+                "max_tokens": 10000
+            })],
+        )
+        .await?;
+
+    // Then: The caller is added, unrelated files are not
+    let markdown = response["markdown"].as_str().unwrap();
+    assert!(markdown.contains("math.rs"));
+    assert!(markdown.contains("main.rs"));
+    assert!(!markdown.contains("other.rs"));
+
+    Ok(())
+}
+
 /// Test process_local_codebase with path traversal attempt
 #[tokio::test]
 async fn test_process_local_codebase_path_traversal_rejected() -> Result<()> {

```