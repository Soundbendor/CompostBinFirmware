# Example code in C to demonstrate selectivity and IAQ outputs in BME688 with BSEC2 library
 * Example for using of BSEC library in a fixed configuration with the BME68x sensor.
 * This works by running an endless loop in the bsec_iot_loop() function.

# Hardware test details
 * By default all 8 sensors are supported and this can be modified in file "bsec_integration.h" macro "NUM_OF_SENS".
 * The communication mode to the sensor is via SPI in this illustration.

# Algorithm inclusion
 * The static library path needs to be included in the platform.txt file.
 * In the platforms.txt search ‘recipe.c.combine.pattern’ and adding where your library is located after ‘{object_files}’, just like this:
   recipe.c.combine.pattern="{compiler.path}{compiler.c.elf.cmd}" "-Wl,--Map={build.path}/{build.project_name}.map" "-L{compiler.sdk.path}/lib" "-L{compiler.sdk.path}/ld" "-L{compiler.sdk.path}/{build.memory_type}" {compiler.c.elf.flags} {compiler.c.elf.extra_flags} {build.extra_flags} -Wl,--start-group {object_files} "C:\Users\Name\Documents\Projects\Bsec_Library\libalgobsec.a" "{archive_file_path}" {build.extra_libs} {compiler.c.elf.libs} {compiler.libraries.ldflags} -Wl,--end-group -Wl,-EL -o "{build.path}/{build.project_name}.elf"
 * Configurations can be copied to files Selectivity_Config.c & Selectivity_Config.h which is included by default
 * Note to not change the variable name as they are already linked in the repositroy.

# Code compilation
 * You have to bring all the necessary dependent files from src folder(bme68x, config and inc) in order to compile the example code.

# Stack Overflow
 * Few hardwares may have limited stack size by default and needs to be modified inorder to include larger algorithms
 * For arduino environment the stack size is declared in sdkconfig.h file under definition CONFIG_ARDUINO_LOOP_STACK_SIZE

# Switching between the output modes in BSEC
 * At any given time only one mode is supported in BSEC.
 * Change the macro "OUTPUT_MODE" to either "CLASSIFICATION" or "REGRESSION" or "IAQ" based on the requirement in "bsec_integration.h" file.
 * The default "OUTPUT_MODE" in the code is "CLASSIFICATION".
 * Ensure to copy the appropriate config files based on the output mode.
 * IAQ output is supported in both classification and regression config file.
 * "SAMPLE_RATE" depends on the "OUTPUT_MODE",
 	* If the "OUTPUT_MODE"  value is "CLASSIFICATION" (or) "REGRESSION", the "SAMPLE_RATE" assigned is "BSEC_SAMPLE_RATE_SCAN" (default).
 	* If the "OUTPUT_MODE" value is "IAQ", the "SAMPLE_RATE" assigned is "BSEC_SAMPLE_RATE_ULP" (default).
	* For the "OUTPUT_MODE" as "IAQ" the other supported "SAMPLE_RATE" is "BSEC_SAMPLE_RATE_CONT" (or) "BSEC_SAMPLE_RATE_LP".