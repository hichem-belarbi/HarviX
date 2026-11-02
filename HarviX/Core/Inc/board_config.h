#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

#include "stm32f4xx_hal.h"

/* ============================================================
 *  STM32F429I-DISC1 — Allocation des pins
 *
 *  Capteurs :
 *    SPI1  (3 slots)  — PA5/PA6/PA7 + CS PB0/PB1/PB2
 *    SPI4  (2 slots)  — PE2/PE5/PE6 + CS PE3/PE4
 *    I2C2  (1 slot)   — PF0/PF1     (jusqu'à 6 devices)
 *    I2C3  (1 slot)   — PA8/PC9     (jusqu'à 6 devices)
 *    ADC1  (5 slots)  — PA1/PA2/PA3/PC0/PC2
 *    Digital (2 slots)— PD14/PD15   (TIM4 CH3/CH4)
 *
 *  Communication :
 *    USB OTG CDC      — PB14/PB15   (CN6, streaming principal)
 *    USART1 VCP       — PA9/PA10    (CN1 ST-LINK, debug)
 *
 *  Stockage :
 *    SPI3 SD card     — PC10/PC11/PC12/PD2
 *
 *  Affichage :
 *    I2C1 LCD 16×2    — PB6/PB7     (bus dédié)
 *
 *  Actions :
 *    GPIO sorties     — PD0/PD1/PD3/PD4
 *    PWM servos       — PD12/PD13   (TIM4 CH1/CH2)
 *
 *  Interface :
 *    Boutons menu     — PE7/PE8/PE9/PE10
 *    LEDs carte       — PG13 (vert) / PG14 (rouge)
 *    Bouton USER      — PA0
 * ============================================================ */

/* ============================================================
 *  Nombre de slots par type de bus
 * ============================================================ */
#define NB_SPI_SLOTS      5
#define NB_I2C_SLOTS      2
#define NB_ADC_SLOTS      5
#define NB_DIGITAL_SLOTS  2
#define NB_SLOTS          (NB_SPI_SLOTS + NB_I2C_SLOTS + \
                           NB_ADC_SLOTS + NB_DIGITAL_SLOTS)

/* ============================================================
 *  Handles HAL — définis dans main.c par CubeMX
 * ============================================================ */
extern SPI_HandleTypeDef  hspi1;
extern SPI_HandleTypeDef  hspi3;     /* SD card            */
extern SPI_HandleTypeDef  hspi4;
extern I2C_HandleTypeDef  hi2c1;     /* LCD                */
extern I2C_HandleTypeDef  hi2c2;     /* capteurs           */
extern I2C_HandleTypeDef  hi2c3;     /* capteurs           */
extern ADC_HandleTypeDef  hadc1;
extern TIM_HandleTypeDef  htim4;     /* servos + digital   */

/* ============================================================
 *  Slots SPI — bus 1 (SPI1, 3 slots)
 *  PA5 = SCK, PA6 = MISO, PA7 = MOSI
 * ============================================================ */
#define CH1_BUS           BUS_SPI
#define CH1_SPI_HANDLE    (&hspi1)
#define CH1_CS_PORT       GPIOB
#define CH1_CS_PIN        GPIO_PIN_0

#define CH2_BUS           BUS_SPI
#define CH2_SPI_HANDLE    (&hspi1)
#define CH2_CS_PORT       GPIOB
#define CH2_CS_PIN        GPIO_PIN_1

#define CH3_BUS           BUS_SPI
#define CH3_SPI_HANDLE    (&hspi1)
#define CH3_CS_PORT       GPIOB
#define CH3_CS_PIN        GPIO_PIN_2

/* ============================================================
 *  Slots SPI — bus 2 (SPI4, 2 slots)
 *  PE2 = SCK, PE5 = MISO, PE6 = MOSI
 * ============================================================ */
#define CH4_BUS           BUS_SPI
#define CH4_SPI_HANDLE    (&hspi4)
#define CH4_CS_PORT       GPIOE
#define CH4_CS_PIN        GPIO_PIN_3

#define CH5_BUS           BUS_SPI
#define CH5_SPI_HANDLE    (&hspi4)
#define CH5_CS_PORT       GPIOE
#define CH5_CS_PIN        GPIO_PIN_4

/* ============================================================
 *  Slots I2C — capteurs (2 bus indépendants)
 * ============================================================ */
#define CH6_BUS           BUS_I2C
#define CH6_I2C_HANDLE    (&hi2c2)    /* PF1 = SCL, PF0 = SDA */

#define CH7_BUS           BUS_I2C
#define CH7_I2C_HANDLE    (&hi2c3)    /* PA8 = SCL, PC9 = SDA */

/* ============================================================
 *  Slots ADC — capteurs analogiques (5 canaux)
 * ============================================================ */
#define CH8_BUS           BUS_ADC
#define CH8_ADC_HANDLE    (&hadc1)
#define CH8_ADC_CHANNEL   ADC_CHANNEL_1     /* PA1 */

#define CH9_BUS           BUS_ADC
#define CH9_ADC_HANDLE    (&hadc1)
#define CH9_ADC_CHANNEL   ADC_CHANNEL_2     /* PA2 */

#define CH10_BUS          BUS_ADC
#define CH10_ADC_HANDLE   (&hadc1)
#define CH10_ADC_CHANNEL  ADC_CHANNEL_3     /* PA3 */

#define CH11_BUS          BUS_ADC
#define CH11_ADC_HANDLE   (&hadc1)
#define CH11_ADC_CHANNEL  ADC_CHANNEL_10    /* PC0 */

#define CH12_BUS          BUS_ADC
#define CH12_ADC_HANDLE   (&hadc1)
#define CH12_ADC_CHANNEL  ADC_CHANNEL_12    /* PC2 */

/* ============================================================
 *  Slots Digital — capteurs 1-wire (DHT11, DHT22, DS18B20)
 *  Partagent TIM4 avec les servos (CH1/CH2 PWM, CH3/CH4 capture)
 * ============================================================ */
#define CH13_BUS              BUS_DIGITAL
#define CH13_DIGITAL_PORT     GPIOD
#define CH13_DIGITAL_PIN      GPIO_PIN_14   /* PD14 = TIM4_CH3 */
#define CH13_TIM_HANDLE       (&htim4)
#define CH13_TIM_CHANNEL      TIM_CHANNEL_3

#define CH14_BUS              BUS_DIGITAL
#define CH14_DIGITAL_PORT     GPIOD
#define CH14_DIGITAL_PIN      GPIO_PIN_15   /* PD15 = TIM4_CH4 */
#define CH14_TIM_HANDLE       (&htim4)
#define CH14_TIM_CHANNEL      TIM_CHANNEL_4

/* ============================================================
 *  LCD I2C (bus dédié, pas un slot capteur)
 *  I2C1 : PB6 = SCL, PB7 = SDA
 * ============================================================ */
#define LCD_I2C_HANDLE        (&hi2c1)
#define LCD_I2C_ADDRESS       (0x27 << 1)

/* ============================================================
 *  SD Card (bus dédié)
 *  SPI3 : PC10 = SCK, PC11 = MISO, PC12 = MOSI, PD2 = CS
 * ============================================================ */
#define SD_SPI_HANDLE         (&hspi3)
#define SD_CS_PORT            GPIOD
#define SD_CS_PIN             GPIO_PIN_2

/* ============================================================
 *  Actions hardware — 4 sorties GPIO + 2 servos PWM
 * ============================================================ */
#define NB_ACTION_PINS        4
#define ACTION_PIN1_PORT      GPIOD
#define ACTION_PIN1_PIN       GPIO_PIN_1
#define ACTION_PIN2_PORT      GPIOG
#define ACTION_PIN2_PIN       GPIO_PIN_13
#define ACTION_PIN3_PORT      GPIOD
#define ACTION_PIN3_PIN       GPIO_PIN_3
#define ACTION_PIN4_PORT      GPIOD
#define ACTION_PIN4_PIN       GPIO_PIN_4

#define NB_SERVOS             2
#define SERVO1_TIM_HANDLE     (&htim4)
#define SERVO1_TIM_CHANNEL    TIM_CHANNEL_1   /* PD12 */
#define SERVO2_TIM_HANDLE     (&htim4)
#define SERVO2_TIM_CHANNEL    TIM_CHANNEL_2   /* PD13 */

/* ============================================================
 *  Boutons menu — 4 GPIO input pull-up
 * ============================================================ */
#define BTN_UP_PORT           GPIOE
#define BTN_UP_PIN            GPIO_PIN_7
#define BTN_DOWN_PORT         GPIOE
#define BTN_DOWN_PIN          GPIO_PIN_8
#define BTN_SELECT_PORT       GPIOE
#define BTN_SELECT_PIN        GPIO_PIN_9
#define BTN_BACK_PORT         GPIOE
#define BTN_BACK_PIN          GPIO_PIN_10

/* ============================================================
 *  LEDs système
 * ============================================================ */
#define LED_OK_PORT           GPIOG
#define LED_OK_PIN            GPIO_PIN_13
#define LED_ERR_PORT          GPIOG
#define LED_ERR_PIN           GPIO_PIN_14

#endif
