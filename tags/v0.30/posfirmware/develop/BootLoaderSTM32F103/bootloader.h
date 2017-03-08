#include <stdio.h>
#include "stm32f10x.h"                            // Their STM32F10x Definitions (most of which I am not using) 
#include "CAN.h"                                  // STM32 CAN adaption layer
#include "STM32F103_Registers.h"   								// My file with register location defines
#include "custom_flash_functions.h"

typedef  void (*pFunction)(void);

#define  CAN1_RxRdy          					((uint32_t)0x00000001)
#define  CAN2_RxRdy           				((uint32_t)0x00000002)
#define  STREG_2        							((uint32_t)0x00000004)
#define  STREG_3				    					((uint32_t)0x00000008)
#define  STREG_4    									((uint32_t)0x00000010)
#define  STREG_5            					((uint32_t)0x00000020)
#define  STREG_6            					((uint32_t)0x00000040)
#define  STREG_7            					((uint32_t)0x00000080)

#define  FLASH_RW_Start								((uint32_t)0x00000100)	/* 1 -> si l'application a déjà commencé à être écrite dans la mémoire flash */
#define  FLASH_RW_Stop								((uint32_t)0x00000200)	/* 1 -> si l'application a fini d'être écrite dans la mémoire flash */
#define  READY_TO_RUN_APP							((uint32_t)0x00000400)
#define  STREG_11          						((uint32_t)0x00000800)
#define  STREG_12            					((uint32_t)0x00001000)
#define  STREG_13											((uint32_t)0x00002000)
#define  STREG_14            					((uint32_t)0x00004000)
#define  STREG_15            					((uint32_t)0x00008000)

#define  STREG_16            					((uint32_t)0x00010000)
#define  STREG_17            					((uint32_t)0x00020000)
#define  STREG_18            					((uint32_t)0x00040000)
#define  STREG_19            					((uint32_t)0x00080000)
#define  STREG_20            					((uint32_t)0x00100000)
#define  STREG_21            					((uint32_t)0x00200000)
#define  STREG_22            					((uint32_t)0x00400000)
#define  STREG_23           					((uint32_t)0x00800000)

#define  STREG_24        							((uint32_t)0x01000000) 	//1 -> wrong step count over 1 rotation
#define  STREG_25            					((uint32_t)0x02000000)
#define  STREG_26            					((uint32_t)0x04000000)
#define  STREG_27            					((uint32_t)0x08000000)
#define  STREG_28            					((uint32_t)0x10000000)
#define  STREG_29            					((uint32_t)0x20000000)
#define  STREG_30            					((uint32_t)0x40000000)
#define  STREG_31            					((uint32_t)0x80000000)

void flash_PA4(int leng);
void flash_PA5(int leng);
void flash_PA6(int leng);
void flash_PA7(int leng);
void Delay (uint32_t dlyTicks);
