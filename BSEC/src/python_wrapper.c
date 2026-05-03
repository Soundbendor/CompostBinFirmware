/**
 * Copyright (C) 2018 Bosch Sensortec GmbH
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 *
 * Redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution.
 *
 * Neither the name of the copyright holder nor the names of the
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
 * CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL COPYRIGHT HOLDER
 * OR CONTRIBUTORS BE LIABLE FOR ANY
 * DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
 * OR CONSEQUENTIAL DAMAGES(INCLUDING, BUT NOT LIMITED TO,
 * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 * LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 * ANY WAY OUT OF THE USE OF THIS
 * SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE
 *
 * The information provided is believed to be accurate and reliable.
 * The copyright holder assumes no responsibility
 * for the consequences of use
 * of such information nor for any infringement of patents or
 * other rights of third parties which may result from its use.
 * No license is granted by implication or otherwise under any patent or
 * patent rights of the copyright holder.
 *
 * @file    bsec_iot_example.c
 * @date    Dec-10-2018
 * @version 1.1
 *
 */

/*!
 * @brief
 * Example for using of BSEC library in a fixed configuration with the BME680 sensor.
 * This works by running an endless loop in the bsec_iot_loop() function.
 */

/*!
 * @addtogroup bsec_examples BSEC Examples
 * @brief BSEC usage examples
 * @{*/

/**********************************************************************************************************************/
/* header files */
/**********************************************************************************************************************/

/*********************************************************************/
/* system header files */
#include "time.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>
#include <getopt.h>
#include <string.h>

/*********************************************************************/
/* Own header files */
#include "../include/bsec_integration_backend.h"


/**********************************************************************************************************************/
/* functions */
/**********************************************************************************************************************/

/*!
 * @brief           System specific implementation of sleep function
 *
 * @param[in]       t_ms    time in milliseconds
 *
 * @return          none
 */
void sleep(uint32_t t_ms){}


/*!
 * @brief           Load previous library state from non-volatile memory
 *
 * @param[in,out]   state_buffer    buffer to hold the loaded state string
 * @param[in]       n_buffer        size of the allocated state buffer
 *
 * @return          number of bytes copied to state_buffer
 */
uint32_t state_load(uint8_t *state_buffer, uint32_t n_buffer)
{
    FILE *fptr;
    char line[1000];
    fptr = fopen("savedState.dat", "r");
    if (fptr == NULL)
        return 0;
    fscanf(fptr, "%[^\n]", line);
    int length = atoi(line);
    uint8_t character = 0;
    fgetc(fptr);

    for(int i = 0; i < length; i++){
        character = fgetc(fptr);
        state_buffer[i] = character;
    }
    return length;
}

/*!
 * @brief           Save library state to non-volatile memory
 *
 * @param[in]       state_buffer    buffer holding the state to be stored
 * @param[in]       length          length of the state string to be stored
 *
 * @return          none
 */
void state_save(const uint8_t *state_buffer, uint32_t length)
{
    FILE *fptr;
    fptr = fopen("savedState.dat", "w");
    fprintf(fptr, "%u\n", length);
    for(int i = 0; i < length; i++){
        fputc(state_buffer[i], fptr);
    }
    fclose(fptr);
}

static int bsec_initialized = 0;

int proccess_bme_data(int ts, float temperature, float pressure, float humidity, float gas_resistance, float output[7]){
    if (!bsec_initialized) {
        return_values_init ret_bsec;
        /* Call to the function which initializes the BSEC library 
         * Switch on low-power mode and provide no temperature offset */
        ret_bsec = bsec_iot_init_backend(BSEC_SAMPLE_RATE_LP, 0.0f, state_load);
        if (ret_bsec.bme680_status)
        {
            /* Could not intialize BME680 */
            return (int)ret_bsec.bme680_status;
        }
        else if (ret_bsec.bsec_status)
        {
            /* Could not intialize BSEC library */
            return (int)ret_bsec.bsec_status;
        }
        bsec_initialized = 1;
    }
	

    /* Call a loop function which reads and processes data based on provided raw data file. */
    /* State is optionally saved every 10.000 samples, which means every 10.000 * 3 secs = 500 minutes */
	bsec_iot_loop_backend(ts, temperature,pressure,humidity,gas_resistance,output, state_save);

   
	
    return 0;
}

/*! @}*/

