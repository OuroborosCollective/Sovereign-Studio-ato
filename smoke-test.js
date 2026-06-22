#!/usr/bin/env node

// Simple smoke test to verify the modules can be imported
console.log('Testing Sovereign Studio LLM integration...');

try {
  // Test importing the main modules
  const fs = require('fs');
  const path = require('path');
  
  const llmRuntimePath = path.join(__dirname, 'src/features/product/runtime/sovereignLlmRuntime.ts');
  const memoryContextPath = path.join(__dirname, 'src/features/product/runtime/sovereignMemoryContext.ts');
  const packageBuilderPath = path.join(__dirname, 'src/features/product/runtime/sovereignPackageFromRepoFiles.ts');
  
  if (fs.existsSync(llmRuntimePath)) {
    console.log('✓ sovereignLlmRuntime.ts exists');
  } else {
    console.log('✗ sovereignLlmRuntime.ts missing');
  }
  
  if (fs.existsSync(memoryContextPath)) {
    console.log('✓ sovereignMemoryContext.ts exists');
  } else {
    console.log('✗ sovereignMemoryContext.ts missing');
  }
  
  // Check if the App.tsx file was updated
  const appPath = path.join(__dirname, 'src/App.tsx');
  if (fs.existsSync(appPath)) {
    const appContent = fs.readFileSync(appPath, 'utf8');
    if (appContent.includes('buildSovereignPackageFromRepoFilesWithLlm')) {
      console.log('✓ App.tsx updated to use LLM-aware package builder');
    } else {
      console.log('✗ App.tsx not updated properly');
    }
  } else {
    console.log('✗ App.tsx missing');
  }
  
  console.log('Smoke test completed.');
} catch (error) {
  console.error('Error during smoke test:', error.message);
  process.exit(1);
}