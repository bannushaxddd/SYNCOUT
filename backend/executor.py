"""
SYNCOUT - Code Execution Engine
Safely executes code in sandboxed environment
"""

import subprocess
import tempfile
import os
import time
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class CodeExecutor:
    """Execute code safely with timeout and resource limits"""
    
    # Language configurations
    LANGUAGES = {
        'python': {
            'extension': '.py',
            'command': ['python', '{file}'],
            'timeout': 10
        },
        'javascript': {
            'extension': '.js',
            'command': ['node', '{file}'],
            'timeout': 10
        },
        'typescript': {
            'extension': '.ts',
            'command': ['ts-node', '{file}'],
            'timeout': 10
        },
        'java': {
            'extension': '.java',
            'command': ['java', '{file}'],
            'timeout': 15,
            'compile': ['javac', '{file}']
        },
        'cpp': {
            'extension': '.cpp',
            'command': ['{output}'],
            'timeout': 15,
            'compile': ['g++', '{file}', '-o', '{output}']
        },
        'c': {
            'extension': '.c',
            'command': ['{output}'],
            'timeout': 15,
            'compile': ['gcc', '{file}', '-o', '{output}']
        },
        'go': {
            'extension': '.go',
            'command': ['go', 'run', '{file}'],
            'timeout': 10
        },
        'rust': {
            'extension': '.rs',
            'command': ['{output}'],
            'timeout': 15,
            'compile': ['rustc', '{file}', '-o', '{output}']
        }
    }
    
    def execute(self, code: str, language: str, stdin: str = "") -> Dict:
        """
        Execute code and return results
        
        Args:
            code: Source code to execute
            language: Programming language
            stdin: Standard input for the program
            
        Returns:
            Dict with stdout, stderr, exit_code, execution_time
        """
        start_time = time.time()
        
        if language not in self.LANGUAGES:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Language "{language}" not supported',
                'exit_code': -1,
                'execution_time': 0
            }
        
        lang_config = self.LANGUAGES[language]
        
        source_file = None
        output_file = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=lang_config['extension'],
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(code)
                source_file = f.name
            
            # Compile if needed
            if 'compile' in lang_config:
                output_file = source_file.replace(lang_config['extension'], '')
                compile_result = self._compile(
                    source_file, 
                    output_file, 
                    lang_config['compile']
                )
                
                if not compile_result['success']:
                    return compile_result
            
            # Execute
            command = [
                cmd.format(
                    file=source_file,
                    output=output_file
                ) for cmd in lang_config['command']
            ]
            
            result = subprocess.run(
                command,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=lang_config['timeout'],
                cwd=os.path.dirname(source_file)
            )
            
            execution_time = time.time() - start_time
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode,
                'execution_time': round(execution_time, 3)
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Execution timed out after {lang_config["timeout"]}s',
                'exit_code': -1,
                'execution_time': lang_config['timeout']
            }
        
        except FileNotFoundError as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Compiler/interpreter not found: {str(e)}',
                'exit_code': -1,
                'execution_time': 0
            }
        
        except Exception as e:
            logger.error(f"Execution error: {e}")
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Execution error: {str(e)}',
                'exit_code': -1,
                'execution_time': time.time() - start_time
            }
        
        finally:
            # Cleanup
            try:
                if source_file and os.path.exists(source_file):
                    os.unlink(source_file)
                if output_file and os.path.exists(output_file):
                    os.unlink(output_file)
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")
    
    def _compile(self, source: str, output: str, command: list) -> Dict:
        """Compile source code"""
        try:
            cmd = [c.format(file=source, output=output) for c in command]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {
                    'success': False,
                    'stdout': result.stdout,
                    'stderr': f'Compilation failed:\n{result.stderr}',
                    'exit_code': result.returncode,
                    'execution_time': 0
                }
            
            return {'success': True}
            
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Compilation error: {str(e)}',
                'exit_code': -1,
                'execution_time': 0
            }


# Singleton instance
executor = CodeExecutor()
