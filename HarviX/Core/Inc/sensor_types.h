#ifndef SENSOR_TYPES_H
#define SENSOR_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include "stm32f4xx_hal.h"
#include "board_config.h"

/* ============================================================
 *  Limites du système
 *  Déduites de board_config.h — ne pas modifier ici.
 * ============================================================ */
#define MAX_I2C_DEVICES_PER_SLOT   6
#define MAX_DEVICES_PER_SLOT       MAX_I2C_DEVICES_PER_SLOT
#define MAX_TOTAL_DEVICES          (NB_SPI_SLOTS + NB_ADC_SLOTS + \
                                    NB_DIGITAL_SLOTS + \
                                    (NB_I2C_SLOTS * MAX_I2C_DEVICES_PER_SLOT))

/* ============================================================
 *  Types de bus physiques
 * ============================================================ */
typedef enum {
    BUS_NONE = 0,
    BUS_SPI,
    BUS_I2C,
    BUS_ADC,
    BUS_DIGITAL,
} Bus_Type_t;

/* ============================================================
 *  Modèles de capteurs supportés
 * ============================================================ */
typedef enum {
    SENSOR_NONE = 0,
    SENSOR_BMP280,
    SENSOR_AHT20,
    SENSOR_BH1750,
    SENSOR_INA219,
    SENSOR_LM75,
    SENSOR_NTC,
    SENSOR_DHT11,
    SENSOR_DHT22,
    SENSOR_DS18B20,
    SENSOR_COUNT
} Sensor_Model_t;

/* ============================================================
 *  Grandeurs physiques mesurables
 * ============================================================ */
typedef enum {
    QUANTITY_NONE = 0,
    QUANTITY_TEMPERATURE,    /* °C  */
    QUANTITY_PRESSURE,       /* Pa  */
    QUANTITY_HUMIDITY,       /* %RH */
    QUANTITY_VOLTAGE,        /* V   */
    QUANTITY_LIGHT_LUX,      /* lx  */
    QUANTITY_BUS_VOLTAGE,    /* V   */
    QUANTITY_SHUNT_VOLTAGE,  /* mV  */
    QUANTITY_CURRENT,        /* mA  */
    QUANTITY_POWER,          /* mW  */
    QUANTITY_COUNT
} Physical_Quantity_t;

/* ============================================================
 *  Déclarations anticipées (forward declarations)
 *
 *  Nécessaires car il y a des dépendances croisées par pointeur :
 *    - Device_t contient un pointeur vers Sensor_Driver_API_t
 *    - Sensor_Driver_API_t.init prend des pointeurs vers Slot_t
 *      et Device_t
 *
 *  Les structs anonymes (typedef struct { ... } Foo_t) ne peuvent
 *  PAS être forward-déclarées en C. On utilise donc des struct
 *  nommées : typedef struct Foo_s { ... } Foo_t.
 * ============================================================ */
typedef struct Slot_s               Slot_t;
typedef struct Device_s             Device_t;
typedef struct Sensor_Driver_API_s  Sensor_Driver_API_t;

/* ============================================================
 *  Descripteurs hardware des bus
 * ============================================================ */
typedef struct {

    GPIO_TypeDef      *cs_port;
    uint16_t           cs_pin;
} Bus_SPI_HW_t;

typedef struct {
    I2C_HandleTypeDef *handle;
} Bus_I2C_HW_t;

typedef struct {
    ADC_HandleTypeDef *handle;
    uint32_t           channel;
} Bus_ADC_HW_t;

typedef struct {
    GPIO_TypeDef      *port;
    uint16_t           pin;
    TIM_HandleTypeDef *timer;
    uint32_t           timer_channel;
} Bus_Digital_HW_t;

/* ============================================================
 *  Mesure individuelle — une grandeur d'un device
 * ============================================================ */
typedef struct {
    uint8_t             uid;
    uint8_t             slot_id;
    Sensor_Model_t      model;
    Physical_Quantity_t quantity;
    float               value;
    uint32_t            timestamp_ms;
    int8_t              status;     /* 0 = ok, négatif = erreur */
} Measurement_t;

/* ============================================================
 *  Snapshot — toutes les mesures d'un tick
 *  Publié atomiquement dans la queue à chaque période.
 * ============================================================ */
typedef struct {
    uint32_t      timestamp_ms;
    Measurement_t measures[MAX_TOTAL_DEVICES];
    uint8_t       count;
} Snapshot_t;

/* ============================================================
 *  Paramètres passés lors de l'assignation d'un capteur
 * ============================================================ */
typedef struct {
    uint8_t i2c_address;
    uint8_t raw[16];
} Sensor_Params_t;

/* ============================================================
 *  Device — un capteur assigné à un slot
 *
 *  1 device = 1 capteur physique mesurant 1 grandeur.
 *  Utilise la forward declaration de Sensor_Driver_API_t
 *  (pointeur seulement — le compilateur n'a pas besoin de
 *  connaître la taille de la struct à ce stade).
 * ============================================================ */
struct Device_s {
    uint8_t                    uid;
    bool                       occupied;
    Sensor_Model_t             model;
    Physical_Quantity_t        quantity;
    uint8_t                    i2c_address;
    const Sensor_Driver_API_t *driver;        /* forward déclaré */
    void                      *driver_handle;
    bool                       initialized;

    /* Diagnostic */
    uint32_t                   read_count;
    uint32_t                   error_count;
};

/* ============================================================
 *  Slot — port physique sur la carte
 *
 *  SPI     : 1 device max  (discriminant = CS pin)
 *  ADC     : 1 device max  (discriminant = channel)
 *  Digital : 1 device max  (discriminant = GPIO pin)
 *  I2C     : MAX_I2C_DEVICES_PER_SLOT devices max
 *            (discriminant = adresse I2C)
 * ============================================================ */
struct Slot_s {
    uint8_t    slot_id;
    Bus_Type_t bus_type;

    union {
        Bus_SPI_HW_t     spi;
        Bus_I2C_HW_t     i2c;
        Bus_ADC_HW_t     adc;
        Bus_Digital_HW_t digital;
    } hw;

    Device_t devices[MAX_DEVICES_PER_SLOT];
    uint8_t  device_count;
};

/* ============================================================
 *  API d'un driver de capteur
 *
 *  Défini en dernier car les fonctions init/read prennent
 *  des pointeurs vers Slot_t et Device_t (déjà définis).
 * ============================================================ */
struct Sensor_Driver_API_s {
    int  (*init)(Slot_t *slot, Device_t *device, void **handle);
    int  (*read)(void *handle, Physical_Quantity_t quantity, Measurement_t *out);
    void (*deinit)(void *handle);
    bool (*supports_bus)(Bus_Type_t bus);
    bool (*supports_quantity)(Physical_Quantity_t quantity);
};

#endif /* SENSOR_TYPES_H */
