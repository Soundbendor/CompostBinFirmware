/**
 * Copyright (C) Bosch Sensortec GmbH. All Rights Reserved. Confidential.
 *
 * Disclaimer
 *
 * Common:
 * Bosch Sensortec products are developed for the consumer goods industry. They may only be used
 * within the parameters of the respective valid product data sheet. Bosch Sensortec products are
 * provided with the express understanding that there is no warranty of fitness for a particular purpose.
 * They are not fit for use in life-sustaining, safety or security sensitive systems or any system or device
 * that may lead to bodily harm or property damage if the system or device malfunctions. In addition,
 * Bosch Sensortec products are not fit for use in products which interact with motor vehicle systems.
 * The resale and/or use of products are at the purchaser's own risk and his own responsibility. The
 * examination of fitness for the intended use is the sole responsibility of the Purchaser.
 *
 * The purchaser shall indemnify Bosch Sensortec from all third party claims, including any claims for
 * incidental, or consequential damages, arising from any product use not covered by the parameters of
 * the respective valid product data sheet or not approved by Bosch Sensortec and reimburse Bosch
 * Sensortec for all costs in connection with such claims.
 *
 * The purchaser must monitor the market for the purchased products, particularly with regard to
 * product safety and inform Bosch Sensortec without delay of all security relevant incidents.
 *
 * Engineering Samples are marked with an asterisk (*) or (e). Samples may vary from the valid
 * technical specifications of the product series. They are therefore not intended or fit for resale to third
 * parties or for use in end products. Their sole purpose is internal client testing. The testing of an
 * engineering sample may in no way replace the testing of a product series. Bosch Sensortec
 * assumes no liability for the use of engineering samples. By accepting the engineering samples, the
 * Purchaser agrees to indemnify Bosch Sensortec from all claims arising from the use of engineering
 * samples.
 *
 * Special:
 * This software module (hereinafter called "Software") and any information on application-sheets
 * (hereinafter called "Information") is provided free of charge for the sole purpose to support your
 * application work. The Software and Information is subject to the following terms and conditions:
 *
 * The Software is specifically designed for the exclusive use for Bosch Sensortec products by
 * personnel who have special experience and training. Do not use this Software if you do not have the
 * proper experience or training.
 *
 * This Software package is provided `` as is `` and without any expressed or implied warranties,
 * including without limitation, the implied warranties of merchantability and fitness for a particular
 * purpose.
 *
 * Bosch Sensortec and their representatives and agents deny any liability for the functional impairment
 * of this Software in terms of fitness, performance and safety. Bosch Sensortec and their
 * representatives and agents shall not be liable for any direct or indirect damages or injury, except as
 * otherwise stipulated in mandatory applicable law.
 *
 * The Information provided is believed to be accurate and reliable. Bosch Sensortec assumes no
 * responsibility for the consequences of use of such Information nor for any infringement of patents or
 * other rights of third parties which may result from its use. No license is granted by implication or
 * otherwise under any patent or patent rights of Bosch. Specifications mentioned in the Information are
 * subject to change without notice.
 *
 * It is not allowed to deliver the source code of the Software to any third party without permission of
 * Bosch Sensortec.
 *
 */

/*!
 * @file bsec_iot_example.ino
 *
 * @brief
 * Example for using of BSEC library in a fixed configuration with the BME68x sensor.
 * This works by running an endless loop in the bsec_iot_loop() function.
 */

/*!
 * @addtogroup bsec_examples BSEC Examples
 * @brief BSEC usage examples
 * @{*/

/**********************************************************************************************************************/
/* header files */
/**********************************************************************************************************************/

#include "bsec_integration.h"
#include "commMux.h"
#include "bsec_selectivity.h"
#include <Wire.h>

String output;
uint32_t overflowCounter;
uint32_t lastTimeMS;
commMux communicationSetup[NUM_OF_SENS];

/**********************************************************************************************************************/
/* functions */
/**********************************************************************************************************************/

/*!
 * @brief           Write operation in either Wire or SPI
 *
 * param[in]        reg_addr        register address
 * param[in]        reg_data_ptr    pointer to the data to be written
 * param[in]        data_len        number of bytes to be written
 * param[in]        intf_ptr        interface pointer
 *
 * @return          result of the bus communication function
 */
int8_t bus_write(uint8_t reg_addr, const uint8_t *reg_data_ptr, uint32_t data_len, void *intf_ptr)
{
    uint8_t dev_addr = *(uint8_t*)intf_ptr;
    
    Wire.beginTransmission(dev_addr);
    Wire.write(reg_addr);    /* Set register address to start writing to */
 
    /* Write the data */
    for (int index = 0; index < data_len; index++) {
        Wire.write(reg_data_ptr[index]);
    }
 
    return (int8_t)Wire.endTransmission();
}

/*!
 * @brief           Read operation in either Wire or SPI
 *
 * param[in]        reg_addr        register address
 * param[out]       reg_data_ptr    pointer to the memory to be used to store the read data
 * param[in]        data_len        number of bytes to be read
 * param[in]        intf_ptr        interface pointer
 * 
 * @return          result of the bus communication function
 */
int8_t bus_read(uint8_t reg_addr, uint8_t *reg_data_ptr, uint32_t data_len, void *intf_ptr)
{
    int8_t comResult = 0;
    uint8_t dev_addr = *(uint8_t*)intf_ptr;
    Wire.beginTransmission(dev_addr);
    Wire.write(reg_addr);                    /* Set register address to start reading from */
    comResult = Wire.endTransmission();
 
    delayMicroseconds(150);                 /* Precautionary response delay */
    Wire.requestFrom(dev_addr, (uint8_t)data_len);    /* Request data */
 
    int index = 0;
    while (Wire.available())  /* The slave device may send less than requested (burst read) */
    {
        reg_data_ptr[index] = Wire.read();
        index++;
    }
 
    return comResult;
}

/*!
 * @brief           System specific implementation of sleep function
 *
 * @param[in]       t_us     Time in microseconds
 * @param[in]       intf_ptr Pointer to the interface descriptor
 * 
 * @return          none
 */
void sleep_n(uint32_t t_us, void *intf_ptr)
{
  delay(t_us / 1000);
}

/*!
 * @brief           Capture the system time in microseconds
 *
 * @return          system_current_time    current system timestamp in microseconds
 */
int64_t get_timestamp_us()
{
    int64_t timeMs = millis() * 1000;

    if (lastTimeMS > timeMs) /* An overflow occurred */
    { 
        overflowCounter++;
    }
    lastTimeMS = timeMs;
    
    return timeMs + (overflowCounter * INT64_C(0xFFFFFFFF));
}

/*!
 * @brief           Handling of the ready outputs
 *
 * @param[in]       outputs                 output_t structure
 * @param[in]       bsec_status             value returned by the bsec_do_steps() call
 *
 * @return          none
 */
void output_ready(output_t *outputs, bsec_library_return_t bsec_status)
{
  digitalWrite(LED_BUILTIN, LOW);
  float timestamp_ms = outputs->timestamp/1e6;

  output = String(outputs->sens_no) + ",";
  output += String(timestamp_ms) + ", ";

#if (OUTPUT_MODE == CLASSIFICATION || OUTPUT_MODE == REGRESSION)
  output += String(outputs->gas_estimate_1) + ", ";
  output += String(outputs->gas_estimate_2) + ", ";
  output += String(outputs->gas_estimate_3) + ", ";
  output += String(outputs->gas_estimate_4) + ", ";
  output += String(outputs->gas_accuracy_1) + ", ";
  output += String(outputs->gas_accuracy_2) + ", ";
  output += String(outputs->gas_accuracy_3) + ", ";
  output += String(outputs->gas_accuracy_4) + ", ";
  output += String(outputs->raw_pressure) + ", ";
  output += String(outputs->raw_temp) + ", ";
  output += String(outputs->raw_humidity) + ", ";
  output += String(outputs->raw_gas) + ", ";
  output += String(outputs->raw_gas_index) + ", ";
#elif (OUTPUT_MODE == IAQ)
  output += String(outputs->iaq) + ", ";
  output += String(outputs->iaq_accuracy) + ", ";
  output += String(outputs->static_iaq) + ", ";
  output += String(outputs->raw_temp) + ", ";
  output += String(outputs->raw_humidity) + ", ";
  output += String(outputs->temperature) + ", ";
  output += String(outputs->humidity) + ", ";
  output += String(outputs->raw_pressure) + ", "; 
  output += String(outputs->raw_gas) + ", ";
  output += String(outputs->gas_percentage) + ", ";
  output += String(outputs->co2_equivalent) + ", ";
  output += String(outputs->breath_voc_equivalent) + ", ";
  output += String(outputs->stabStatus) + ", ";
  output += String(outputs->runInStatus) + ", ";
  output += String(outputs->compensated_gas) + ", ";
#endif

  output += String(bsec_status);
  Serial.println(output);
  digitalWrite(LED_BUILTIN, HIGH);
}

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
    // ...
    // Load a previous library state from non-volatile memory, if available.
    //
    // Return zero if loading was unsuccessful or no state was available, 
    // otherwise return length of loaded state string.
    // ...
    return 0;
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
    // ...
    // Save the string some form of non-volatile memory, if possible.
    // ...
}

/*!
 * @brief           Load library config from non-volatile memory
 *
 * @param[in,out]   config_buffer    buffer to hold the loaded state string
 * @param[in]       n_buffer        size of the allocated state buffer
 *
 * @return          number of bytes copied to config_buffer
 */
uint32_t config_load(uint8_t *config_buffer, uint32_t n_buffer)
{
	memcpy(config_buffer, bsec_config_selectivity, n_buffer);
    return n_buffer;
}

/*!
 * @brief       Main function which configures BSEC library and then reads and processes the data from sensor based
 *              on timer ticks
 *
 * @return      result of the processing
 */
void setup()
{
    return_values_init ret;
    pinMode(LED_BUILTIN, OUTPUT);
    /* Init I2C and serial communication */
    Wire.begin();
    commMuxBegin(Wire, SPI);
    Serial.begin(115200);
    delay(1000);

	struct bme68x_dev bme_dev[NUM_OF_SENS];
  
	for (uint8_t i = 0; i < NUM_OF_SENS; i++) {

		/* Sets the Communication interface for the given sensor */
		communicationSetup[i] = commMuxSetConfig(Wire, SPI, i/*SENS_NUM*/, communicationSetup[i]);

		memset(&bme_dev[i],0,sizeof(bme_dev[i]));
		bme_dev[i].intf = BME68X_SPI_INTF;
		bme_dev[i].read = commMuxRead;
		bme_dev[i].write = commMuxWrite;
		bme_dev[i].delay_us = commMuxDelay;
		bme_dev[i].intf_ptr = &communicationSetup[i];
		bme_dev[i].amb_temp = 25;

		/* Assigning a chunk of memory block to the bsecInstance */
		allocateMemory(bsec_mem_block[i], i);

		/* Call to the function which initializes the BSEC library
		* Switch on low-power mode and provide no temperature offset */
		ret = bsec_iot_init(SAMPLE_RATE, 0.0f, bus_write, bus_read, sleep_n, state_load, config_load, bme_dev[i], i);

		if (ret.bme68x_status)
		{
			/* Could not initialize BME68x */
			Serial.println("ERROR while initializing BME68x:"+String(ret.bme68x_status));
			return;
		}
		else if (ret.bsec_status < BSEC_OK)
		{
			printf("\nERROR while initializing BSEC library: %d\n", ret.bsec_status);
			return;
		}
		else if (ret.bsec_status > BSEC_OK)
		{
			printf("\nWARNING while initializing BSEC library: %d\n", ret.bsec_status);
		}
	}

	bsec_version_t version;
	bsec_get_version_m(bsecInstance, &version);
	Serial.println("\nBSEC library version " + String(version.major) + "." + String(version.minor) + "." \
					+ String(version.major_bugfix) + "." + String(version.minor_bugfix));

#if (OUTPUT_MODE == CLASSIFICATION || OUTPUT_MODE == REGRESSION)
    String file_header = "\nSensor_No, Time(ms), Class/Target_1_prediction, Class/Target_2_prediction, Class/Target_3_prediction, Class/Target_4_prediction, Prediction_accuracy_1, Prediction_accuracy_2, Prediction_accuracy_3, Prediction_accuracy_4, Raw_pressure(Pa), Raw_Temperature(degC),  Raw_Humidity(%rH), Raw_Gas(ohm), Raw_Gas_Index(num), Bsec_status";
#elif (OUTPUT_MODE == IAQ)
	String file_header = "\nSensor_No, Time(ms), IAQ, IAQ_accuracy, Static_IAQ, Raw_Temperature(degC), Raw_Humidity(%rH), Comp_Temperature(degC),  Comp_Humidity(%rH), Raw_pressure(Pa), Raw_Gas(ohms), Gas_percentage, CO2, bVOC, Stabilization_status, Run_in_status, Compensated_gas, Bsec_status";
#endif
  
	Serial.println(file_header);
    /* Call to endless loop function which reads and processes data based on sensor settings */
    /* State is saved every 10.000 samples, which means every 10.000 * 3 secs = 500 minutes  */
    bsec_iot_loop(sleep_n, get_timestamp_us, output_ready, state_save, 10000);
}

void loop()
{
}

/*! @}*/
