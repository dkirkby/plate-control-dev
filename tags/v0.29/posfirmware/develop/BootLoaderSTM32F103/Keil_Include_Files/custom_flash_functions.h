#ifndef __FLASH_RW_FUNCTION_H
#define __FLASH_RW_FUNCTION_H

#ifdef __cplusplus
 extern "C" {
#endif

/* Include */
#include "../bootloader.h"
#include "stm32f10x_flash.h"

/* Base address of the Flash pages */
#define 	ADDR_FLASH_PAGE_0				((uint32_t)0x08000000) /* Base @ of Page 0, 2 Kbytes */
#define 	ADDR_FLASH_PAGE_1      	((uint32_t)0x08000800) /* Base @ of Page 1, 2 Kbytes */
#define 	ADDR_FLASH_PAGE_2      	((uint32_t)0x08001000) /* Base @ of PAGE 2, 2 Kbytes */
#define 	ADDR_FLASH_PAGE_3      	((uint32_t)0x08001800) /* Base @ of PAGE 3, 2 Kbytes */
// etc...
#define   ADDR_FLASH_PAGE_62		 	((uint32_t)0x0801F000) /* Base @ of PAGE 100, 2 Kbytes */	 
// etc...
#define 	ADDR_FLASH_PAGE_255    	((uint32_t)0x0807F800) /* Base @ of PAGE 255, 2 Kbytes */

#define 	APPLI_START_ADDR 				ADDR_FLASH_PAGE_62

void EraseFlashForApplication(uint32_t Start_Address, uint32_t End_Address);
uint32_t WriteRxBuffer(uint32_t Start_Address);
void jump2Appli(void);
uint32_t GetFlashPage(uint32_t Address);

#ifdef __cplusplus
}
#endif

#endif 
